"""
MAVLink mission upload, verification, and clear protocol implementation.

Upload handshake (GCS → Vehicle):
  1. GCS → MISSION_COUNT(n)
  2. Vehicle → MISSION_REQUEST_INT(seq)    ← for each item the vehicle wants
  3. GCS → MISSION_ITEM_INT(seq)           ← always respond to the REQUESTED seq
  4. Repeat 2–3 until all items sent
  5. Vehicle → MISSION_ACK(ACCEPTED)

Verification (read-back after upload):
  1. GCS → MISSION_REQUEST_LIST
  2. Vehicle → MISSION_COUNT(n)
  3. For each i: GCS → MISSION_REQUEST_INT(i), Vehicle → MISSION_ITEM_INT(i)
  4. Compare every field with the in-memory Mission object

All incoming message I/O goes through connection.register_waiter() so the
background receiver thread cannot consume protocol messages before this module
can read them.  Never call master.recv_match() directly.
"""
import logging
import queue
import time

from pymavlink import mavutil

from config import settings
from mavlink.connection import MAVLinkConnection
from models.mission import Mission, WaypointItem

logger = logging.getLogger(__name__)

_UPLOAD_TOTAL_TIMEOUT = 60.0   # seconds — covers 1000-waypoint missions
_ITEM_REQUEST_TIMEOUT = 5.0    # per-item request timeout
_ACK_TIMEOUT          = 5.0    # MISSION_ACK / COMMAND_ACK timeout
_VERIFY_ITEM_TIMEOUT  = 5.0    # per-item download timeout during verification


class MissionUploadError(RuntimeError):
    """Raised when mission upload or verification fails."""


class MissionUploader:
    """Implements the MAVLink mission upload, verification, and clear protocols."""

    def __init__(self, conn: MAVLinkConnection) -> None:
        self._conn = conn

    # ── Public API ─────────────────────────────────────────────────────────────

    def clear_mission(self) -> bool:
        """
        Send MISSION_CLEAR_ALL and wait for MISSION_ACK.

        Uses register_waiter() so the MISSION_ACK is not consumed by the
        background receiver thread.
        """
        m = self._require_master()
        logger.info("→ MISSION_CLEAR_ALL sent.")

        q = self._conn.register_waiter("MISSION_ACK")
        try:
            m.mav.mission_clear_all_send(
                m.target_system,
                m.target_component,
                mavutil.mavlink.MAV_MISSION_TYPE_MISSION,
            )
            if settings.DEBUG_MAVLINK:
                logger.info("[MAVLink TX] MISSION_CLEAR_ALL")

            try:
                ack = q.get(timeout=_ACK_TIMEOUT)
            except queue.Empty:
                logger.warning(
                    "MISSION_CLEAR_ALL: no MISSION_ACK within %.1fs. "
                    "Assuming cleared (vehicle may have accepted silently).",
                    _ACK_TIMEOUT,
                )
                return False
        finally:
            self._conn.unregister_waiter("MISSION_ACK")

        if ack.type == mavutil.mavlink.MAV_MISSION_ACCEPTED:
            logger.info("← MISSION_ACK received: mission cleared.")
            return True

        logger.warning(
            "MISSION_CLEAR_ALL rejected by vehicle: MISSION_ACK type=%s (%d).",
            _ack_type_name(ack.type), ack.type,
        )
        return False

    def upload_mission(self, mission: Mission) -> bool:
        """
        Upload a Mission to the vehicle using the full MAVLink handshake.

        Protocol:
          GCS sends MISSION_COUNT(n)
          Vehicle sends MISSION_REQUEST_INT(seq) for each item it wants
          GCS responds with MISSION_ITEM_INT for the REQUESTED seq (not sequential assumption)
          Vehicle sends MISSION_ACK when done

        The receiver thread is excluded from reading mission protocol messages
        via register_waiter() for the duration of this call.

        Returns True on success, raises MissionUploadError on failure.
        """
        m = self._require_master()
        waypoints = mission.waypoints
        count = len(waypoints)

        if count == 0:
            raise MissionUploadError("Cannot upload an empty mission.")

        logger.info(
            "Starting mission upload: %d items from '%s' (format=%s).",
            count, mission.filename, mission.source_format,
        )

        _WAIT_TYPES = ("MISSION_REQUEST_INT", "MISSION_REQUEST", "MISSION_ACK")
        q = self._conn.register_waiter(*_WAIT_TYPES)
        try:
            return self._do_upload(m, waypoints, count, q)
        finally:
            self._conn.unregister_waiter(*_WAIT_TYPES)

    def verify_mission(self, mission: Mission) -> tuple[bool, str]:
        """
        Download the mission from the vehicle and compare with the local copy.

        Returns (True, success_message) or (False, error_detail).
        Every waypoint's command, latitude, longitude, and altitude is checked.
        """
        m = self._require_master()
        waypoints = mission.waypoints
        expected_count = len(waypoints)

        logger.info(
            "Starting mission verification (expecting %d items).", expected_count
        )

        # Phase 1: request item count
        q_count = self._conn.register_waiter("MISSION_COUNT")
        try:
            m.mav.mission_request_list_send(
                m.target_system,
                m.target_component,
                mavutil.mavlink.MAV_MISSION_TYPE_MISSION,
            )
            logger.info("→ MISSION_REQUEST_LIST sent.")
            if settings.DEBUG_MAVLINK:
                logger.info("[MAVLink TX] MISSION_REQUEST_LIST")

            try:
                count_msg = q_count.get(timeout=5.0)
            except queue.Empty:
                return (
                    False,
                    "Mission verification failed: timeout waiting for MISSION_COUNT. "
                    "Vehicle may not have stored the mission.",
                )
        finally:
            self._conn.unregister_waiter("MISSION_COUNT")

        vehicle_count = count_msg.count
        logger.info(
            "← MISSION_COUNT received: vehicle has %d items (expected %d).",
            vehicle_count, expected_count,
        )

        if vehicle_count != expected_count:
            return (
                False,
                f"Mission verification failed: vehicle has {vehicle_count} items, "
                f"expected {expected_count}.",
            )

        # Phase 2: download each item and compare
        q_items = self._conn.register_waiter("MISSION_ITEM_INT", "MISSION_ITEM")
        mismatches: list[str] = []
        try:
            for i in range(expected_count):
                m.mav.mission_request_int_send(
                    m.target_system,
                    m.target_component,
                    i,
                    mavutil.mavlink.MAV_MISSION_TYPE_MISSION,
                )
                if settings.DEBUG_MAVLINK:
                    logger.info("[MAVLink TX] MISSION_REQUEST_INT seq=%d", i)

                try:
                    item_msg = q_items.get(timeout=_VERIFY_ITEM_TIMEOUT)
                except queue.Empty:
                    return (
                        False,
                        f"Mission verification failed: timeout downloading item {i}.",
                    )

                msg_type = item_msg.get_type()
                logger.debug("← %s received (seq=%d).", msg_type, i)

                errs = self._compare_waypoint(
                    waypoints[i], item_msg, i, is_int=(msg_type == "MISSION_ITEM_INT")
                )
                mismatches.extend(errs)
        finally:
            self._conn.unregister_waiter("MISSION_ITEM_INT", "MISSION_ITEM")

        if mismatches:
            detail = "; ".join(mismatches[:5])
            return False, f"Mission verification failed — mismatches: {detail}"

        ok_msg = f"Mission verified: {expected_count} items match."
        logger.info(ok_msg)
        return True, ok_msg

    # ── Internal ───────────────────────────────────────────────────────────────

    def _do_upload(self, m, waypoints: list[WaypointItem], count: int, q: queue.Queue) -> bool:
        """Inner upload loop — runs with waiter already registered."""
        # Announce how many items we're uploading
        m.mav.mission_count_send(
            m.target_system,
            m.target_component,
            count,
            mavutil.mavlink.MAV_MISSION_TYPE_MISSION,
        )
        logger.info("→ MISSION_COUNT sent (count=%d).", count)
        if settings.DEBUG_MAVLINK:
            logger.info("[MAVLink TX] MISSION_COUNT count=%d", count)

        items_sent = 0          # highest (seq+1) ever sent — survives retransmit
        deadline = time.monotonic() + _UPLOAD_TOTAL_TIMEOUT

        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            try:
                msg = q.get(timeout=min(_ITEM_REQUEST_TIMEOUT, remaining))
            except queue.Empty:
                raise MissionUploadError(
                    f"Vehicle stopped responding after {items_sent}/{count} items sent. "
                    f"No MISSION_REQUEST_INT received within {_ITEM_REQUEST_TIMEOUT}s."
                )

            msg_type = msg.get_type()

            # ── MISSION_ACK — upload complete (or rejected) ────────────────────
            if msg_type == "MISSION_ACK":
                ack_type = msg.type
                logger.info(
                    "← MISSION_ACK received: %s (%d).",
                    _ack_type_name(ack_type), ack_type,
                )
                if ack_type == mavutil.mavlink.MAV_MISSION_ACCEPTED:
                    logger.info("Mission upload complete — %d items accepted.", count)
                    return True
                raise MissionUploadError(
                    f"Vehicle rejected mission upload. "
                    f"MISSION_ACK = {_ack_type_name(ack_type)} (type={ack_type}). "
                    "Check mission items for unsupported frames or commands."
                )

            # ── MISSION_REQUEST_INT or MISSION_REQUEST ─────────────────────────
            seq = msg.seq
            logger.info("← %s received (seq=%d).", msg_type, seq)

            if seq >= count:
                raise MissionUploadError(
                    f"Vehicle requested out-of-range item seq={seq} "
                    f"(mission has {count} items)."
                )

            wp = waypoints[seq]
            use_int = (msg_type == "MISSION_REQUEST_INT")
            self._send_item(m, wp, seq, use_int=use_int)
            logger.info(
                "→ MISSION_ITEM_INT sent (seq=%d  cmd=%d  lat=%.6f  lon=%.6f  alt=%.2f).",
                seq, wp.command, wp.latitude, wp.longitude, wp.altitude,
            )

            # Track highest seq sent (handles retransmit requests without decrementing)
            items_sent = max(items_sent, seq + 1)

        raise MissionUploadError(
            f"Mission upload timed out after {_UPLOAD_TOTAL_TIMEOUT}s. "
            f"Sent {items_sent}/{count} items."
        )

    def _send_item(self, master, wp: WaypointItem, seq: int, use_int: bool) -> None:
        if settings.DEBUG_MAVLINK:
            logger.info(
                "[MAVLink TX] MISSION_ITEM_INT seq=%d frame=%d cmd=%d "
                "current=%d autocontinue=%d "
                "p1=%.3f p2=%.3f p3=%.3f p4=%.3f "
                "lat=%d lon=%d alt=%.3f",
                seq, wp.frame, wp.command,
                1 if wp.current else 0, int(wp.autocontinue),
                wp.param1, wp.param2, wp.param3, wp.param4,
                int(wp.latitude * 1e7), int(wp.longitude * 1e7), wp.altitude,
            )

        if use_int:
            master.mav.mission_item_int_send(
                master.target_system,
                master.target_component,
                seq,
                wp.frame,
                wp.command,
                1 if wp.current else 0,
                int(wp.autocontinue),
                wp.param1,
                wp.param2,
                wp.param3,
                wp.param4,
                int(wp.latitude * 1e7),
                int(wp.longitude * 1e7),
                wp.altitude,
                mavutil.mavlink.MAV_MISSION_TYPE_MISSION,
            )
        else:
            # Fallback: vehicle sent MISSION_REQUEST (non-INT, legacy firmware)
            master.mav.mission_item_send(
                master.target_system,
                master.target_component,
                seq,
                wp.frame,
                wp.command,
                1 if wp.current else 0,
                int(wp.autocontinue),
                wp.param1,
                wp.param2,
                wp.param3,
                wp.param4,
                wp.latitude,
                wp.longitude,
                wp.altitude,
                mavutil.mavlink.MAV_MISSION_TYPE_MISSION,
            )

    def _compare_waypoint(
        self, wp: WaypointItem, msg, idx: int, is_int: bool
    ) -> list[str]:
        """Return a list of mismatch descriptions (empty = match)."""
        errors: list[str] = []

        if msg.command != wp.command:
            errors.append(
                f"item[{idx}] command: expected {wp.command}, got {msg.command}"
            )

        if is_int:
            veh_lat = msg.x / 1e7
            veh_lon = msg.y / 1e7
        else:
            veh_lat = float(msg.x)
            veh_lon = float(msg.y)
        veh_alt = float(msg.z)

        # 1e-5 degrees ≈ 1 m on Earth's surface; accounts for float↔int32 round-trip
        if wp.latitude != 0.0 and abs(veh_lat - wp.latitude) > 1e-5:
            errors.append(
                f"item[{idx}] latitude: expected {wp.latitude:.6f}, got {veh_lat:.6f}"
            )
        if wp.longitude != 0.0 and abs(veh_lon - wp.longitude) > 1e-5:
            errors.append(
                f"item[{idx}] longitude: expected {wp.longitude:.6f}, got {veh_lon:.6f}"
            )
        if abs(veh_alt - wp.altitude) > 0.5:
            errors.append(
                f"item[{idx}] altitude: expected {wp.altitude:.2f} m, got {veh_alt:.2f} m"
            )

        return errors

    def _require_master(self):
        if not self._conn.master:
            raise RuntimeError(
                "Not connected to Pixhawk. Use POST /connect before uploading."
            )
        return self._conn.master


# ── Helpers ────────────────────────────────────────────────────────────────────

def _ack_type_name(ack_type: int) -> str:
    """Return a human-readable name for a MAV_MISSION_RESULT value."""
    _NAMES = {
        0:  "MAV_MISSION_ACCEPTED",
        1:  "MAV_MISSION_ERROR",
        2:  "MAV_MISSION_UNSUPPORTED_FRAME",
        3:  "MAV_MISSION_UNSUPPORTED",
        4:  "MAV_MISSION_NO_SPACE",
        5:  "MAV_MISSION_INVALID",
        6:  "MAV_MISSION_INVALID_PARAM1",
        7:  "MAV_MISSION_INVALID_PARAM2",
        8:  "MAV_MISSION_INVALID_PARAM3",
        9:  "MAV_MISSION_INVALID_PARAM4",
        10: "MAV_MISSION_INVALID_PARAM5_X",
        11: "MAV_MISSION_INVALID_PARAM6_Y",
        12: "MAV_MISSION_INVALID_PARAM7",
        13: "MAV_MISSION_INVALID_SEQUENCE",
        14: "MAV_MISSION_DENIED",
        15: "MAV_MISSION_OPERATION_CANCELLED",
    }
    return _NAMES.get(ack_type, f"UNKNOWN_{ack_type}")
