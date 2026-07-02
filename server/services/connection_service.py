"""
Connection lifecycle service.

Thin orchestration layer between the API route and the MAVLink connection.
Centralises connection state so routes never import pymavlink directly.
"""
import logging
from mavlink.connection import connection, drone_state, DroneState, list_available_ports
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
        return used_port

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
