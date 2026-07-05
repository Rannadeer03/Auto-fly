"""
MAVLink connection manager.

Owns the serial connection to the Pixhawk and maintains a background receiver
thread that continuously reads MAVLink messages and updates the shared DroneState.

KEY DESIGN — waiter queues
==========================
Protocol-level exchanges (mission upload, command acks, mission verification)
require exclusive access to specific incoming message types.  The background
receiver thread now routes any message type that has an active waiter into that
waiter's queue instead of the normal telemetry dispatch.  Protocol handlers call
register_waiter() BEFORE sending their request, then read from the returned queue,
then call unregister_waiter() when done.

This eliminates the race condition where the receiver thread consumed
MISSION_REQUEST_INT / COMMAND_ACK messages before the protocol handler could
read them, causing silent upload and command failures.
"""
import glob
import logging
import math
import platform
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from pymavlink import mavutil

from config import settings

logger = logging.getLogger(__name__)

# ── Flight mode tables (ArduCopter) ───────────────────────────────────────────

ARDUPILOT_MODES: dict[str, int] = {
    "STABILIZE": 0,
    "ACRO": 1,
    "ALT_HOLD": 2,
    "AUTO": 3,
    "GUIDED": 4,
    "LOITER": 5,
    "RTL": 6,
    "CIRCLE": 7,
    "LAND": 9,
    "DRIFT": 11,
    "SPORT": 13,
    "FLIP": 14,
    "AUTOTUNE": 15,
    "POSHOLD": 16,
    "BRAKE": 17,
    "THROW": 18,
    "AVOID_ADSB": 19,
    "GUIDED_NOGPS": 20,
    "SMART_RTL": 21,
    "FLOWHOLD": 22,
    "FOLLOW": 23,
    "ZIGZAG": 24,
}

MODE_BY_NUMBER: dict[int, str] = {v: k for k, v in ARDUPILOT_MODES.items()}

MAV_STATE_NAMES: dict[int, str] = {
    0: "UNINIT",
    1: "BOOT",
    2: "CALIBRATING",
    3: "STANDBY",
    4: "ACTIVE",
    5: "CRITICAL",
    6: "EMERGENCY",
    7: "POWEROFF",
    8: "FLIGHT_TERMINATION",
}

_MAX_CONSECUTIVE_RECEIVE_ERRORS = 5

GPS_FIX_NAMES: dict[int, str] = {
    0: "No GPS",
    1: "No Fix",
    2: "2D Fix",
    3: "3D Fix",
    4: "DGPS",
    5: "RTK Float",
    6: "RTK Fixed",
}


# ── Port detection ─────────────────────────────────────────────────────────────

def detect_pixhawk_port() -> Optional[str]:
    """
    Scan for the first connected Pixhawk / flight-controller serial port.

    macOS:  /dev/cu.usbmodem*  (cu.* preferred — avoids tty.* locking issues)
    Linux:  /dev/ttyACM*  then  /dev/ttyUSB*
    """
    system = platform.system()
    if system == "Darwin":
        patterns = ["/dev/cu.usbmodem*", "/dev/tty.usbmodem*"]
    else:
        patterns = ["/dev/ttyACM*", "/dev/ttyUSB*"]

    for pattern in patterns:
        matches = sorted(glob.glob(pattern))
        if matches:
            return matches[0]
    return None


def list_available_ports() -> list[str]:
    """Return all candidate Pixhawk serial ports found on this system."""
    system = platform.system()
    if system == "Darwin":
        patterns = ["/dev/cu.usbmodem*", "/dev/tty.usbmodem*"]
    else:
        patterns = ["/dev/ttyACM*", "/dev/ttyUSB*"]

    ports: list[str] = []
    for pattern in patterns:
        ports.extend(sorted(glob.glob(pattern)))
    return ports


# ── Shared drone state ─────────────────────────────────────────────────────────

@dataclass
class DroneState:
    """Thread-safe container for all current drone state.

    Updated exclusively by the MAVLink receiver thread; read by any thread
    through snapshot() or individual properties.
    """

    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    # Connection
    connected: bool = False
    last_heartbeat_time: float = 0.0
    heartbeat_count: int = 0
    system_id: int = 1
    component_id: int = 1

    # System
    flight_mode: str = "UNKNOWN"
    armed: bool = False
    system_status: int = 0

    # Position
    latitude: float = 0.0
    longitude: float = 0.0
    altitude_msl: float = 0.0
    altitude_rel: float = 0.0

    # Velocity
    ground_speed: float = 0.0
    air_speed: float = 0.0
    climb_rate: float = 0.0
    heading: int = 0

    # Attitude (degrees)
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0
    roll_speed: float = 0.0
    pitch_speed: float = 0.0
    yaw_speed: float = 0.0

    # GPS
    gps_satellites: int = 0
    gps_fix_type: int = 0
    gps_hdop: float = 99.99
    gps_vdop: float = 99.99

    # Battery
    battery_voltage: float = 0.0
    battery_remaining: int = -1
    battery_current: float = 0.0
    battery_consumed_mah: float = 0.0

    # Mission
    mission_uploaded: bool = False
    waypoint_count: int = 0
    current_waypoint: int = 0
    distance_to_waypoint: float = 0.0
    # Highest waypoint seq confirmed reached (MISSION_ITEM_REACHED). -1 = none yet.
    last_reached_waypoint: int = -1

    # Health flags (from SYS_STATUS sensors bitmask)
    ekf_ok: bool = False
    gyro_ok: bool = False
    accel_ok: bool = False
    baro_ok: bool = False
    compass_ok: bool = False

    def update(self, **kwargs) -> None:
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self, key):
                    setattr(self, key, value)

    def snapshot(self) -> dict:
        """Return a consistent dictionary copy of all non-private fields."""
        with self._lock:
            return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    def reset_flight_data(self) -> None:
        """Clear volatile telemetry without touching mission state."""
        with self._lock:
            self.flight_mode = "UNKNOWN"
            self.armed = False
            self.latitude = self.longitude = 0.0
            self.altitude_msl = self.altitude_rel = 0.0
            self.ground_speed = self.air_speed = self.climb_rate = 0.0
            self.heading = 0
            self.roll = self.pitch = self.yaw = 0.0
            self.gps_satellites = 0
            self.gps_fix_type = 0
            self.battery_voltage = 0.0
            self.battery_remaining = -1
            self.battery_current = 0.0
            self.heartbeat_count = 0
            self.last_heartbeat_time = 0.0
            self.ekf_ok = False

    @property
    def last_heartbeat_ago_s(self) -> float:
        if self.last_heartbeat_time == 0.0:
            return 99.0
        return time.monotonic() - self.last_heartbeat_time

    @property
    def heartbeat_ok(self) -> bool:
        return self.last_heartbeat_ago_s < 5.0


# Module-level singleton — imported by all other modules
drone_state = DroneState()


# ── Connection class ───────────────────────────────────────────────────────────

class MAVLinkConnection:
    """
    Manages the physical MAVLink connection and the message receiver thread.

    Protocol message routing
    ------------------------
    The background receiver thread reads ALL incoming bytes.  For telemetry
    messages (GPS, ATTITUDE, …) it calls the appropriate telemetry handler.
    For protocol messages that an active operation is waiting for (MISSION_REQUEST_INT,
    COMMAND_ACK, …) it puts the message in the caller's queue via the waiter system.

    Callers MUST register_waiter() BEFORE sending the MAVLink request and
    MUST call unregister_waiter() in a finally block after they are done.
    """

    def __init__(self) -> None:
        self._master: Optional[mavutil.mavfile] = None
        self._port: Optional[str] = None
        self._receiver: Optional[threading.Thread] = None
        self._running: bool = False
        self._lock = threading.Lock()
        self.state = drone_state

        # Waiter queues — keyed by MAVLink message type string.
        # When a message type appears here, the receiver routes it to the queue
        # instead of the telemetry handlers.
        self._waiters: dict[str, queue.Queue] = {}
        self._waiters_lock = threading.Lock()

        # Build handler table once — not on every dispatched message.
        self._handlers: dict[str, any] = {
            "HEARTBEAT":             self._on_heartbeat,
            "GPS_RAW_INT":           self._on_gps_raw,
            "GLOBAL_POSITION_INT":   self._on_global_position,
            "VFR_HUD":               self._on_vfr_hud,
            "ATTITUDE":              self._on_attitude,
            "BATTERY_STATUS":        self._on_battery_status,
            "SYS_STATUS":            self._on_sys_status,
            "MISSION_CURRENT":       self._on_mission_current,
            "MISSION_ITEM_REACHED":  self._on_mission_item_reached,
            "NAV_CONTROLLER_OUTPUT": self._on_nav_controller,
            "EKF_STATUS_REPORT":     self._on_ekf_status,
        }

    # ── Waiter API ─────────────────────────────────────────────────────────────

    def register_waiter(self, *msg_types: str) -> "queue.Queue":
        """
        Register interest in one or more MAVLink message types.

        Returns a Queue.  All listed message types will be routed to this queue
        by the receiver thread instead of the telemetry dispatch, until
        unregister_waiter() is called.

        Usage pattern (always use try/finally):
            q = connection.register_waiter("MISSION_REQUEST_INT", "MISSION_ACK")
            try:
                master.mav.mission_count_send(...)
                msg = q.get(timeout=5.0)
            finally:
                connection.unregister_waiter("MISSION_REQUEST_INT", "MISSION_ACK")
        """
        q: queue.Queue = queue.Queue()
        with self._waiters_lock:
            for t in msg_types:
                self._waiters[t] = q
        logger.debug("Waiter registered for: %s", list(msg_types))
        return q

    def unregister_waiter(self, *msg_types: str) -> None:
        """Remove waiter registrations and restore normal telemetry dispatch."""
        with self._waiters_lock:
            for t in msg_types:
                self._waiters.pop(t, None)
        logger.debug("Waiter unregistered for: %s", list(msg_types))

    # ── Public interface ───────────────────────────────────────────────────────

    @property
    def master(self) -> Optional[mavutil.mavfile]:
        return self._master

    @property
    def is_connected(self) -> bool:
        return self._master is not None and self._running

    def connect(self, port: str, baud: int, timeout: float = 15.0) -> None:
        """
        Open the serial port, wait for heartbeat, then start the receiver thread.

        If port == "auto", scans for the Pixhawk automatically.

        Raises:
            ConnectionError  — serial port could not be opened, or no port found.
            TimeoutError     — no heartbeat arrived within the timeout.
            RuntimeError     — already connected.
        """
        with self._lock:
            if self._master is not None:
                raise RuntimeError("Already connected. Call disconnect() first.")

            if port == "auto":
                detected = detect_pixhawk_port()
                if detected is None:
                    available = list_available_ports()
                    if available:
                        raise ConnectionError(
                            f"No Pixhawk auto-detected on {available}. "
                            "Specify MAVLINK_PORT explicitly or check USB connection."
                        )
                    raise ConnectionError(
                        "No Pixhawk detected. Check USB cable and Pixhawk power. "
                        "On macOS the port appears as /dev/cu.usbmodem*."
                    )
                logger.info("Auto-detected Pixhawk port: %s", detected)
                port = detected

            logger.info("Opening MAVLink connection on %s @ %d baud.", port, baud)
            try:
                master = mavutil.mavlink_connection(port, baud=baud, autoreconnect=False)
            except Exception as exc:
                raise ConnectionError(
                    f"Failed to open serial port {port}: {exc}. "
                    "Check the cable, permissions (/dev/ access), and baud rate."
                ) from exc

            logger.info("Waiting for HEARTBEAT on %s (timeout=%.1fs)…", port, timeout)
            hb = master.wait_heartbeat(timeout=timeout)
            if hb is None:
                master.close()
                raise TimeoutError(
                    f"No HEARTBEAT from Pixhawk within {timeout}s on {port}. "
                    "Ensure Pixhawk is powered, firmware is running, and baud "
                    f"rate {baud} matches the Pixhawk MAVLink port setting."
                )

            self._port = port
            self._master = master
            self._running = True

            self.state.update(
                connected=True,
                last_heartbeat_time=time.monotonic(),
                system_id=master.target_system,
                component_id=master.target_component,
                flight_mode=self._decode_mode(hb.custom_mode, hb.base_mode),
                armed=bool(hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED),
                system_status=hb.system_status,
            )

            self._receiver = threading.Thread(
                target=self._receiver_loop,
                name="mavlink-receiver",
                daemon=True,
            )
            self._receiver.start()

            # ArduPilot only pushes GPS_RAW_INT/GLOBAL_POSITION_INT/SYS_STATUS/
            # MISSION_CURRENT/etc. on a link if something requests them —
            # HEARTBEAT is the only message sent unconditionally. QGroundControl
            # always sends this request on connect, which is why it sees live
            # GPS while a link that skips this step sees nothing but heartbeats.
            self._request_data_streams(master)

            logger.info(
                "Connected to Pixhawk on %s — system_id=%d  mode=%s  armed=%s",
                port, master.target_system,
                self.state.flight_mode, self.state.armed,
            )

    def _request_data_streams(self, master) -> None:
        """Ask the vehicle to start streaming telemetry on this link.

        Uses the legacy REQUEST_DATA_STREAM message (still honoured by
        ArduPilot for every stream group via MAV_DATA_STREAM_ALL) rather than
        per-message SET_MESSAGE_INTERVAL — one message, broadly compatible,
        and exactly what MAVProxy/QGroundControl do on connect.
        """
        try:
            master.mav.request_data_stream_send(
                master.target_system,
                master.target_component,
                mavutil.mavlink.MAV_DATA_STREAM_ALL,
                settings.TELEMETRY_STREAM_RATE_HZ,
                1,  # start
            )
            logger.info(
                "→ REQUEST_DATA_STREAM sent (ALL streams @ %d Hz).",
                settings.TELEMETRY_STREAM_RATE_HZ,
            )
        except Exception:
            logger.exception("Failed to send REQUEST_DATA_STREAM — telemetry may stay empty.")

    def disconnect(self) -> None:
        """Stop the receiver thread and close the serial port."""
        with self._lock:
            self._running = False

        if self._receiver and self._receiver.is_alive():
            self._receiver.join(timeout=3.0)

        with self._lock:
            if self._master:
                try:
                    self._master.close()
                except Exception:
                    pass
                self._master = None
            self._port = None

        self.state.update(connected=False)
        self.state.reset_flight_data()
        logger.info("Disconnected from Pixhawk.")

    # ── Receiver loop ──────────────────────────────────────────────────────────

    def _receiver_loop(self) -> None:
        logger.debug("MAVLink receiver thread started.")
        consecutive_errors = 0
        while self._running and self._master:
            try:
                msg = self._master.recv_match(blocking=True, timeout=1.0)
                consecutive_errors = 0
                if msg is not None and msg.get_type() != "BAD_DATA":
                    self._dispatch(msg)
            except Exception as exc:
                if not self._running:
                    break
                consecutive_errors += 1
                logger.warning(
                    "Receiver error (%d/%d consecutive): %s",
                    consecutive_errors, _MAX_CONSECUTIVE_RECEIVE_ERRORS, exc,
                )
                if consecutive_errors >= _MAX_CONSECUTIVE_RECEIVE_ERRORS:
                    logger.error(
                        "Receiver link appears dead after %d consecutive errors — "
                        "tearing down so the link supervisor can reconnect.",
                        consecutive_errors,
                    )
                    self._kill_dead_link()
                    break
                time.sleep(0.05)
        logger.debug("MAVLink receiver thread stopped.")

    def _kill_dead_link(self) -> None:
        """Tear down a connection whose receive loop can no longer read anything.

        Without this, a broken serial port left the receiver spinning on
        exceptions forever while drone_state.connected stayed True — every
        telemetry field (position, battery, GPS, ...) froze at its last
        value with no indication anything was wrong. Mirrors disconnect()'s
        cleanup but runs from inside the receiver thread itself, so it must
        not join() (that would deadlock joining its own thread) — the link
        supervisor's regular "not connected -> reconnect" poll takes it from
        here.
        """
        with self._lock:
            self._running = False
            if self._master:
                try:
                    self._master.close()
                except Exception:
                    pass
                self._master = None
            self._port = None
        self.state.update(connected=False)
        self.state.reset_flight_data()

    def _dispatch(self, msg) -> None:
        msg_type = msg.get_type()

        if settings.DEBUG_MAVLINK:
            logger.info("[MAVLink RX] %s %s", msg_type, msg)

        # ── Route to waiter FIRST ──────────────────────────────────────────────
        # Protocol handlers (upload, command acks) register waiters before
        # sending a request.  If a waiter is registered for this type, put
        # the message in its queue and skip the telemetry dispatch entirely.
        with self._waiters_lock:
            waiter = self._waiters.get(msg_type)
        if waiter is not None:
            try:
                waiter.put_nowait(msg)
            except queue.Full:
                logger.warning("Waiter queue full for %s — message dropped.", msg_type)
            return

        # ── Normal telemetry dispatch ──────────────────────────────────────────
        handler = self._handlers.get(msg_type)
        if handler:
            try:
                handler(msg)
            except Exception as exc:
                logger.debug("Handler error [%s]: %s", msg_type, exc)

    # ── Message handlers ───────────────────────────────────────────────────────

    def _on_heartbeat(self, msg) -> None:
        if msg.type == mavutil.mavlink.MAV_TYPE_GCS:
            return
        if settings.LOG_TELEMETRY_RX:  # TEMP DEBUG — remove once hardware telemetry is confirmed
            logger.info(
                "[RX HEARTBEAT] type=%d autopilot=%d base_mode=%d custom_mode=%d "
                "system_status=%d armed=%s",
                msg.type, msg.autopilot, msg.base_mode, msg.custom_mode, msg.system_status,
                bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED),
            )
        self.state.update(
            connected=True,
            last_heartbeat_time=time.monotonic(),
            heartbeat_count=self.state.heartbeat_count + 1,
            armed=bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED),
            flight_mode=self._decode_mode(msg.custom_mode, msg.base_mode),
            system_status=msg.system_status,
        )

    def _on_gps_raw(self, msg) -> None:
        hdop = msg.eph / 100.0 if msg.eph != 65535 else 99.99
        vdop = msg.epv / 100.0 if msg.epv != 65535 else 99.99
        if settings.LOG_TELEMETRY_RX:  # TEMP DEBUG — remove once hardware telemetry is confirmed
            logger.info(
                "[RX GPS_RAW_INT] fix_type=%d satellites_visible=%d eph=%d epv=%d lat=%d lon=%d",
                msg.fix_type, msg.satellites_visible, msg.eph, msg.epv, msg.lat, msg.lon,
            )
        self.state.update(
            gps_fix_type=msg.fix_type,
            gps_satellites=msg.satellites_visible,
            gps_hdop=hdop,
            gps_vdop=vdop,
        )

    def _on_global_position(self, msg) -> None:
        if settings.LOG_TELEMETRY_RX:  # TEMP DEBUG — remove once hardware telemetry is confirmed
            logger.info(
                "[RX GLOBAL_POSITION_INT] lat=%.7f lon=%.7f alt_msl=%.2f alt_rel=%.2f",
                msg.lat / 1e7, msg.lon / 1e7, msg.alt / 1000.0, msg.relative_alt / 1000.0,
            )
        self.state.update(
            latitude=msg.lat / 1e7,
            longitude=msg.lon / 1e7,
            altitude_msl=msg.alt / 1000.0,
            altitude_rel=msg.relative_alt / 1000.0,
        )

    def _on_vfr_hud(self, msg) -> None:
        # altitude_rel is owned exclusively by _on_global_position
        # (GLOBAL_POSITION_INT) — VFR_HUD's own altitude used to overwrite it
        # too, and the two sources disagreeing depending on arrival order
        # made relative altitude visibly jitter/inconsistent in telemetry.
        self.state.update(
            air_speed=round(msg.airspeed, 2),
            ground_speed=round(msg.groundspeed, 2),
            heading=msg.heading,
            climb_rate=round(msg.climb, 2),
        )

    def _on_attitude(self, msg) -> None:
        self.state.update(
            roll=round(math.degrees(msg.roll), 2),
            pitch=round(math.degrees(msg.pitch), 2),
            yaw=round(math.degrees(msg.yaw), 2),
            roll_speed=round(math.degrees(msg.rollspeed), 2),
            pitch_speed=round(math.degrees(msg.pitchspeed), 2),
            yaw_speed=round(math.degrees(msg.yawspeed), 2),
        )

    def _on_battery_status(self, msg) -> None:
        valid_voltages = [v for v in msg.voltages if v != 65535]
        voltage = (
            sum(valid_voltages) / 1000.0
            if valid_voltages
            else self.state.battery_voltage
        )
        self.state.update(
            battery_voltage=round(voltage, 2),
            battery_remaining=msg.battery_remaining,
            battery_current=(
                round(msg.current_battery / 100.0, 2)
                if msg.current_battery != -1
                else self.state.battery_current
            ),
            battery_consumed_mah=(
                round(msg.current_consumed, 1)
                if msg.current_consumed != -1
                else self.state.battery_consumed_mah
            ),
        )

    def _on_sys_status(self, msg) -> None:
        h = msg.onboard_control_sensors_health
        mav = mavutil.mavlink
        if self.state.battery_voltage == 0.0 and msg.voltage_battery != 65535:
            self.state.update(battery_voltage=round(msg.voltage_battery / 1000.0, 2))
        if self.state.battery_current == 0.0 and msg.current_battery != -1:
            self.state.update(battery_current=round(msg.current_battery / 100.0, 2))
        self.state.update(
            battery_remaining=msg.battery_remaining,
            gyro_ok=bool(h & mav.MAV_SYS_STATUS_SENSOR_3D_GYRO),
            accel_ok=bool(h & mav.MAV_SYS_STATUS_SENSOR_3D_ACCEL),
            baro_ok=bool(h & mav.MAV_SYS_STATUS_SENSOR_ABSOLUTE_PRESSURE),
            compass_ok=bool(h & mav.MAV_SYS_STATUS_SENSOR_3D_MAG),
        )

    def _on_mission_current(self, msg) -> None:
        if settings.LOG_TELEMETRY_RX:  # TEMP DEBUG — remove once hardware telemetry is confirmed
            logger.info("[RX MISSION_CURRENT] seq=%d", msg.seq)
        self.state.update(current_waypoint=msg.seq)

    def _on_mission_item_reached(self, msg) -> None:
        self.state.update(last_reached_waypoint=msg.seq)

    def _on_nav_controller(self, msg) -> None:
        self.state.update(distance_to_waypoint=round(msg.wp_dist, 1))

    def _on_ekf_status(self, msg) -> None:
        ekf_ok = (
            msg.velocity_variance < 1.0
            and msg.pos_horiz_variance < 1.0
            and msg.pos_vert_variance < 1.0
            and msg.compass_variance < 0.8
        )
        self.state.update(ekf_ok=ekf_ok)

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _decode_mode(custom_mode: int, base_mode: int) -> str:
        if base_mode & mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED:
            return MODE_BY_NUMBER.get(custom_mode, f"MODE_{custom_mode}")
        return "MANUAL"


# Module-level singleton — every service imports this object
connection = MAVLinkConnection()
