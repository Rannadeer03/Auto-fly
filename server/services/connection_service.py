"""
Connection lifecycle service.

Thin orchestration layer between the API route and the MAVLink connection.
Centralises connection state so routes never import pymavlink directly.
"""
import logging
from mavlink.connection import connection, drone_state, DroneState, list_available_ports
from mavlink.mission_upload import MissionUploader, MissionUploadError
from config import settings

logger = logging.getLogger(__name__)


class ConnectionService:
    """Manages connect / disconnect lifecycle and port discovery."""

    def connect(self, port: str = None) -> str:
        """
        Open the MAVLink link to the Pixhawk.

        Args:
            port: Serial port override. Defaults to settings.MAVLINK_PORT ("auto").

        Returns:
            The port name actually used (useful when auto-detection chose it).

        Raises:
            RuntimeError:      already connected.
            ConnectionError:   serial port could not be opened or not found.
            TimeoutError:      heartbeat did not arrive in time.
        """
        if drone_state.connected:
            raise RuntimeError("Already connected to the Pixhawk.")

        effective_port = port or settings.MAVLINK_PORT
        connection.connect(
            port=effective_port,
            baud=settings.MAVLINK_BAUD,
            timeout=settings.MAVLINK_TIMEOUT,
        )
        used_port = connection._port or effective_port
        logger.info(
            "Connected to Pixhawk on %s @ %d baud.",
            used_port, settings.MAVLINK_BAUD,
        )
        self._sync_mission_state()
        return used_port

    def _sync_mission_state(self) -> None:
        """Ask the vehicle whether it already has a mission stored, instead
        of only trusting our own upload history.

        drone_state.mission_uploaded is otherwise set exclusively by our own
        /upload and /mission/generate calls (services/mission_service.py) —
        it is never confirmed against the vehicle. A mission uploaded
        directly via QGroundControl, or one that predates a backend
        restart, was therefore invisible to us: ARM/AUTO pre-checks would
        report "No mission loaded on vehicle" even though the vehicle
        genuinely had one.
        """
        try:
            count = MissionUploader(connection).query_mission_count()
        except MissionUploadError as exc:
            logger.warning("Could not sync mission state from vehicle on connect: %s", exc)
            return
        drone_state.update(mission_uploaded=count > 0, waypoint_count=count)
        logger.info("Mission state synced from vehicle: %d item(s) already stored.", count)

    def disconnect(self) -> None:
        """Close the MAVLink link."""
        connection.disconnect()
        logger.info("Disconnected from Pixhawk.")

    def list_ports(self) -> list[str]:
        """Return all candidate serial ports found on this platform."""
        return list_available_ports()

    @property
    def state(self) -> DroneState:
        return drone_state


connection_service = ConnectionService()
