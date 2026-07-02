"""
Telemetry service.

Single entry-point for the /telemetry API endpoint.
Delegates to TelemetryReader which builds the response from DroneState.
"""
from mavlink.telemetry import TelemetryReader
from models.telemetry import TelemetryData


class TelemetryService:
    """Provides current drone telemetry as a Pydantic model."""

    @staticmethod
    def get_telemetry() -> TelemetryData:
        return TelemetryReader.snapshot()


telemetry_service = TelemetryService()
