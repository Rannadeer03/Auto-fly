"""
API routes for flight commands.

Every command validates drone state before issuing the MAVLink command.
Responses include clear failure reasons so the UI can surface them to the user.
"""
import logging
from fastapi import APIRouter
from mavlink.commands import MAVLinkCommands
from mavlink.connection import connection, drone_state
from mavlink.health import HealthChecker
from models.mission import ApiResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["commands"])

_cmds = MAVLinkCommands(connection)
_health = HealthChecker()


def _ok(message: str) -> ApiResponse:
    return ApiResponse(success=True, message=message)


def _fail(message: str) -> ApiResponse:
    logger.warning("Command rejected: %s", message)
    return ApiResponse(success=False, message=message)


@router.post("/arm", response_model=ApiResponse)
async def arm() -> ApiResponse:
    check = _health.check_arm_ready(drone_state)
    if not check:
        return _fail(f"ARM blocked — {check.failure_message()}")
    try:
        if not _cmds.arm():
            return _fail("ARM command rejected by vehicle.")
        return _ok("Drone armed successfully.")
    except Exception as exc:
        logger.exception("ARM error.")
        return _fail(str(exc))


@router.post("/disarm", response_model=ApiResponse)
async def disarm() -> ApiResponse:
    check = _health.check_connected(drone_state)
    if not check:
        return _fail(check.failure_message())
    try:
        if not _cmds.disarm():
            return _fail("DISARM command rejected by vehicle.")
        return _ok("Drone disarmed.")
    except Exception as exc:
        logger.exception("DISARM error.")
        return _fail(str(exc))


@router.post("/start", response_model=ApiResponse)
async def start_mission() -> ApiResponse:
    check = _health.check_auto_ready(drone_state)
    if not check:
        return _fail(f"START blocked — {check.failure_message()}")
    try:
        if not _cmds.start_auto():
            return _fail("Mode change to AUTO rejected by vehicle.")
        return _ok("Mission started in AUTO mode.")
    except Exception as exc:
        logger.exception("START error.")
        return _fail(str(exc))


@router.post("/pause", response_model=ApiResponse)
async def pause_mission() -> ApiResponse:
    check = _health.check_connected(drone_state)
    if not check:
        return _fail(check.failure_message())
    try:
        if not _cmds.pause():
            return _fail("LOITER mode change rejected.")
        return _ok("Mission paused (LOITER).")
    except Exception as exc:
        logger.exception("PAUSE error.")
        return _fail(str(exc))


@router.post("/resume", response_model=ApiResponse)
async def resume_mission() -> ApiResponse:
    check = _health.check_connected(drone_state)
    if not check:
        return _fail(check.failure_message())
    try:
        if not _cmds.resume():
            return _fail("AUTO mode change rejected.")
        return _ok("Mission resumed in AUTO mode.")
    except Exception as exc:
        logger.exception("RESUME error.")
        return _fail(str(exc))


@router.post("/rtl", response_model=ApiResponse)
async def return_to_launch() -> ApiResponse:
    check = _health.check_connected(drone_state)
    if not check:
        return _fail(check.failure_message())
    try:
        if not _cmds.rtl():
            return _fail("RTL mode change rejected.")
        return _ok("Return to Launch initiated.")
    except Exception as exc:
        logger.exception("RTL error.")
        return _fail(str(exc))


@router.post("/land", response_model=ApiResponse)
async def land() -> ApiResponse:
    check = _health.check_connected(drone_state)
    if not check:
        return _fail(check.failure_message())
    try:
        if not _cmds.land():
            return _fail("LAND mode change rejected.")
        return _ok("Landing initiated.")
    except Exception as exc:
        logger.exception("LAND error.")
        return _fail(str(exc))


@router.post("/emergency_stop", response_model=ApiResponse)
async def emergency_stop() -> ApiResponse:
    """Force-disarm immediately. No safety checks — this is intentionally unconditional."""
    logger.critical("EMERGENCY STOP requested via API.")
    try:
        _cmds.emergency_stop()
        return _ok("EMERGENCY STOP executed. Drone force-disarmed.")
    except Exception as exc:
        logger.exception("EMERGENCY STOP error.")
        return _fail(str(exc))
