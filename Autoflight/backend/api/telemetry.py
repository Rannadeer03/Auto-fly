"""API route: GET /telemetry."""
from fastapi import APIRouter
from models.telemetry import TelemetryData
from services.telemetry_service import telemetry_service

router = APIRouter(tags=["telemetry"])


@router.get("/telemetry", response_model=TelemetryData)
async def get_telemetry() -> TelemetryData:
    """Return a current snapshot of all drone telemetry.

    Designed to be polled at 1 Hz by the frontend.
    Response time target: < 10 ms (reads from in-memory state, no I/O).
    """
    return telemetry_service.get_telemetry()
