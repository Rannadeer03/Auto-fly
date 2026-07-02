"""
MAVLink command senders.

Wraps all COMMAND_LONG / mode-change calls so the rest of the codebase
never touches pymavlink directly.

BUG FIX: register_waiter("COMMAND_ACK") is called BEFORE command_long_send,
not after.  This prevents the background receiver thread from consuming
the COMMAND_ACK in the milliseconds between send and recv_match.
"""
import logging
import queue
import time

from pymavlink import mavutil

from config import settings
from mavlink.connection import MAVLinkConnection, ARDUPILOT_MODES

logger = logging.getLogger(__name__)

_ACK_TIMEOUT  = 5.0   # seconds to wait for COMMAND_ACK
_MODE_TIMEOUT = 5.0   # seconds to wait for flight mode to confirm in telemetry


class MAVLinkCommands:
    """High-level flight command interface."""

    def __init__(self, conn: MAVLinkConnection) -> None:
        self._conn = conn

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _master(self):
        if not self._conn.master:
            raise RuntimeError(
                "Not connected to Pixhawk. Use POST /connect first."
            )
        return self._conn.master

    def _send_command_long(
        self,
        command: int,
        p1: float = 0, p2: float = 0, p3: float = 0,
        p4: float = 0, p5: float = 0, p6: float = 0, p7: float = 0,
        confirmation: int = 0,
    ) -> bool:
        """
        Send COMMAND_LONG and wait for COMMAND_ACK.

        The waiter for COMMAND_ACK is registered BEFORE the command is sent
        so the background receiver thread cannot consume the ACK first.
        """
        m = self._master()

        q = self._conn.register_waiter("COMMAND_ACK")
        try:
            m.mav.command_long_send(
                m.target_system,
                m.target_component,
                command,
                confirmation,
                p1, p2, p3, p4, p5, p6, p7,
            )
            if settings.DEBUG_MAVLINK:
                logger.info(
                    "[MAVLink TX] COMMAND_LONG cmd=0x%04X p1=%.1f p2=%.1f",
                    command, p1, p2,
                )
            return self._await_ack(command, q)
        finally:
            self._conn.unregister_waiter("COMMAND_ACK")

    def _await_ack(self, command: int, q: queue.Queue) -> bool:
        """Read COMMAND_ACK from the waiter queue, ignoring ACKs for other commands."""
        deadline = time.monotonic() + _ACK_TIMEOUT
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                ack = q.get(timeout=min(0.5, remaining))
            except queue.Empty:
                continue

            if settings.DEBUG_MAVLINK:
                logger.info(
                    "[MAVLink RX] COMMAND_ACK cmd=0x%04X result=%d (%s)",
                    ack.command, ack.result, _result_name(ack.result),
                )

            if ack.command != command:
                # Stale ACK from a previous command — safe to ignore
                logger.debug(
                    "Ignoring ACK for cmd=0x%04X while waiting for 0x%04X.",
                    ack.command, command,
                )
                continue

            if ack.result == mavutil.mavlink.MAV_RESULT_ACCEPTED:
                logger.info("Command 0x%04X accepted.", command)
                return True

            logger.warning(
                "Command 0x%04X rejected by vehicle: %s (result=%d).",
                command, _result_name(ack.result), ack.result,
            )
            return False

        logger.warning(
            "Command 0x%04X — no COMMAND_ACK within %.1fs. "
            "Vehicle may be busy or command unsupported.",
            command, _ACK_TIMEOUT,
        )
        return False

    def _set_mode_raw(self, mode_name: str) -> bool:
        """
        Switch to a named ArduPilot mode and confirm via heartbeat telemetry.

        Mode changes do not use COMMAND_LONG (pymavlink's set_mode() handles
        the packet format) so no COMMAND_ACK waiter is needed here.
        Confirmation comes from the flight_mode field in the next HEARTBEAT.
        """
        mode_id = ARDUPILOT_MODES.get(mode_name.upper())
        if mode_id is None:
            raise ValueError(f"Unknown ArduPilot mode: '{mode_name}'.")
        m = self._master()
        logger.info("Setting mode → %s (id=%d).", mode_name, mode_id)
        m.set_mode(mode_id)

        deadline = time.monotonic() + _MODE_TIMEOUT
        while time.monotonic() < deadline:
            if self._conn.state.flight_mode.upper() == mode_name.upper():
                logger.info("Mode confirmed via telemetry: %s.", mode_name)
                return True
            time.sleep(0.1)

        logger.warning(
            "Mode change to %s timed out (current telemetry mode=%s). "
            "Vehicle may still be changing modes.",
            mode_name, self._conn.state.flight_mode,
        )
        return False

    # ── Public command API ─────────────────────────────────────────────────────

    def arm(self) -> bool:
        logger.info("Sending ARM command.")
        return self._send_command_long(
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
            p1=1,    # 1 = arm
            p2=0,
        )

    def disarm(self, force: bool = False) -> bool:
        logger.info("Sending DISARM command (force=%s).", force)
        return self._send_command_long(
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
            p1=0,
            p2=21196 if force else 0,   # ArduPilot magic number for force-disarm
        )

    def start_auto(self) -> bool:
        """Switch to AUTO mode to begin executing the uploaded mission."""
        logger.info("Starting AUTO mission.")
        return self._set_mode_raw("AUTO")

    def pause(self) -> bool:
        """Pause mission by switching to LOITER (holds position)."""
        logger.info("Pausing mission → LOITER.")
        return self._set_mode_raw("LOITER")

    def resume(self) -> bool:
        """Resume paused mission by switching back to AUTO."""
        logger.info("Resuming mission → AUTO.")
        return self._set_mode_raw("AUTO")

    def rtl(self) -> bool:
        """Return to launch."""
        logger.info("Initiating RTL.")
        return self._set_mode_raw("RTL")

    def land(self) -> bool:
        """Land in place."""
        logger.info("Initiating LAND.")
        return self._set_mode_raw("LAND")

    def emergency_stop(self) -> bool:
        """Force-disarm the drone immediately, regardless of flight state."""
        logger.critical("EMERGENCY STOP executed.")
        return self.disarm(force=True)

    def set_home_current(self) -> bool:
        """Set home position to current GPS location."""
        return self._send_command_long(
            mavutil.mavlink.MAV_CMD_DO_SET_HOME,
            p1=1,   # use current position
        )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _result_name(result: int) -> str:
    _NAMES = {
        0: "ACCEPTED",
        1: "TEMPORARILY_REJECTED",
        2: "DENIED",
        3: "UNSUPPORTED",
        4: "FAILED",
        5: "IN_PROGRESS",
        6: "CANCELLED",
    }
    return _NAMES.get(result, f"UNKNOWN_{result}")
