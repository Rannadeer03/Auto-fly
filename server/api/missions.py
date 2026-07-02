"""API routes for stored mission data and the active mission session."""
import logging

from fastapi import APIRouter

from services.mission_runner import mission_runner
from services.storage_service import storage_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["missions"])


@router.get("/missions")
async def list_missions() -> dict:
    """List every stored mission folder (video/images/telemetry), newest first."""
    missions = storage_service.list_missions()
    return {"missions": missions, "count": len(missions)}


@router.get("/mission/session")
async def mission_session() -> dict:
    """Status of the active mission automation session (recording, photos)."""
    return mission_runner.get_status()
