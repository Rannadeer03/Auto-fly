"""
Pre-flight safety checks.

By design this module only gates on conditions that make sending the MAVLink
command itself meaningless (no link, no mission loaded) — GPS fix, satellite
count, battery, and EKF health are surfaced to the operator (see
TelemetryData.health / the frontend status banner) but never block ARM or
AUTO from this app. ArduPilot's own EKENS/pre-arm checks and QGroundControl
remain the authority on whether it is actually safe to fly.
"""
import logging
from mavlink.connection import DroneState
from config import settings

logger = logging.getLogger(__name__)


class CheckResult:
    """Carries the outcome of a safety check."""

    def __init__(self, ok: bool, failures: list[str]) -> None:
        self.ok = ok
        self.failures = failures

    def __bool__(self) -> bool:
        return self.ok

    def failure_message(self) -> str:
        return " | ".join(self.failures)


class HealthChecker:
    """Validates drone state before permitting safety-critical operations."""

    def check_arm_ready(self, state: DroneState) -> CheckResult:
        """All conditions that must be true before the ARM command is sent.

        Only a live link and a mission loaded on the vehicle are required —
        GPS fix, satellite count, battery, and EKF are ArduPilot's/QGC's
        responsibility, not this app's. See module docstring.
        """
        failures: list[str] = []

        if not state.connected:
            failures.append("Drone not connected.")
        elif not state.heartbeat_ok:
            failures.append(f"Heartbeat lost ({state.last_heartbeat_ago_s:.1f}s ago).")

        if not state.mission_uploaded:
            failures.append("No mission loaded on vehicle.")

        if failures:
            logger.warning("ARM pre-check failed: %s", " | ".join(failures))

        return CheckResult(len(failures) == 0, failures)

    def check_auto_ready(self, state: DroneState) -> CheckResult:
        """All conditions that must be true before switching to AUTO.

        Only armed + a real mission loaded are required — GPS fix and EKF
        health are ArduPilot's/QGC's responsibility, not this app's. See
        module docstring.
        """
        failures: list[str] = []

        if not state.armed:
            failures.append("Drone is not armed.")
        if not state.mission_uploaded:
            failures.append("No mission loaded on vehicle.")
        if state.waypoint_count < 1:
            failures.append("Mission has no waypoints.")
        if not state.heartbeat_ok:
            failures.append("Heartbeat lost.")

        if failures:
            logger.warning("AUTO pre-check failed: %s", " | ".join(failures))

        return CheckResult(len(failures) == 0, failures)

    def check_connected(self, state: DroneState) -> CheckResult:
        """Minimal check: connection and heartbeat."""
        failures: list[str] = []
        if not state.connected:
            failures.append("Drone not connected.")
        elif not state.heartbeat_ok:
            failures.append(f"Heartbeat lost ({state.last_heartbeat_ago_s:.1f}s ago).")
        return CheckResult(len(failures) == 0, failures)
