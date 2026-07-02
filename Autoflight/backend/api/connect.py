"""API routes: /connect, /disconnect, /ports."""
import logging
from fastapi import APIRouter
from models.mission import ApiResponse
from services.connection_service import connection_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["connection"])


@router.get("/ports")
async def list_ports():
    """
    Return all candidate serial ports found on this system.

    Use this to discover the Pixhawk port before connecting.
    On macOS: /dev/cu.usbmodem*   On Linux: /dev/ttyACM*, /dev/ttyUSB*
    """
    try:
        ports = connection_service.list_ports()
        return {
            "ports": ports,
            "count": len(ports),
            "hint": (
                "These are the serial ports found on this system. "
                "Set MAVLINK_PORT=<port> or leave as 'auto' to auto-detect."
            ),
        }
    except Exception as exc:
        logger.exception("Error listing ports.")
        return {"ports": [], "count": 0, "error": str(exc)}


@router.post("/connect", response_model=ApiResponse)
async def connect_drone() -> ApiResponse:
    """Open MAVLink connection to the Pixhawk (auto-detects port by default)."""
    try:
        port = connection_service.connect()
        return ApiResponse(
            success=True,
            message=f"Connected to Pixhawk on {port}.",
            data={"port": port},
        )
    except RuntimeError as exc:
        return ApiResponse(success=False, message=str(exc))
    except ConnectionError as exc:
        logger.error("Connection failed: %s", exc)
        return ApiResponse(success=False, message=f"Connection failed: {exc}")
    except TimeoutError as exc:
        logger.error("Heartbeat timeout: %s", exc)
        return ApiResponse(success=False, message=f"Heartbeat timeout: {exc}")
    except Exception as exc:
        logger.exception("Unexpected error during connect.")
        return ApiResponse(success=False, message=f"Unexpected error: {exc}")


@router.post("/disconnect", response_model=ApiResponse)
async def disconnect_drone() -> ApiResponse:
    """Close the MAVLink connection."""
    try:
        connection_service.disconnect()
        return ApiResponse(success=True, message="Disconnected from Pixhawk.")
    except Exception as exc:
        logger.exception("Error during disconnect.")
        return ApiResponse(success=False, message=f"Disconnect error: {exc}")
