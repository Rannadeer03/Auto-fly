"""
Pre-flight safety checks.

Every safety-critical operation (ARM, AUTO) goes through this module before
any MAVLink command is sent. No exceptions.
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
        """All conditions that must be true before the ARM command is sent."""
        failures: list[str] = []

        if not state.connected:
            failures.append("Drone not connected.")
        elif not state.heartbeat_ok:
            failures.append(f"Heartbeat lost ({state.last_heartbeat_ago_s:.1f}s ago).")

        if state.battery_voltage > 0 and state.battery_voltage < settings.MIN_BATTERY_VOLTAGE:
            failures.append(
                f"Battery voltage {state.battery_voltage:.1f}V below minimum {settings.MIN_BATTERY_VOLTAGE}V."
            )
        if state.battery_remaining not in (-1,) and state.battery_remaining < settings.MIN_BATTERY_PERCENT:
            failures.append(
                f"Battery {state.battery_remaining}% below minimum {settings.MIN_BATTERY_PERCENT}%."
            )
        if state.gps_fix_type < settings.REQUIRED_GPS_FIX:
            failures.append(
                f"GPS fix type {state.gps_fix_type} insufficient (need ≥{settings.REQUIRED_GPS_FIX})."
            )
        if state.gps_satellites < settings.MIN_GPS_SATELLITES:
            failures.append(
                f"Only {state.gps_satellites} GPS satellites (need ≥{settings.MIN_GPS_SATELLITES})."
            )
        if not state.mission_uploaded:
            failures.append("No mission loaded on vehicle.")

        if failures:
            logger.warning("ARM pre-check failed: %s", " | ".join(failures))

        return CheckResult(len(failures) == 0, failures)

    def check_auto_ready(self, state: DroneState) -> CheckResult:
        """All conditions that must be true before switching to AUTO."""
        failures: list[str] = []

        if not state.armed:
            failures.append("Drone is not armed.")
        if not state.mission_uploaded:
            failures.append("No mission loaded on vehicle.")
        if state.waypoint_count < 1:
            failures.append("Mission has no waypoints.")
        if not state.ekf_ok:
            failures.append("EKF not healthy — check sensors.")
        if state.gps_fix_type < settings.REQUIRED_GPS_FIX:
            failures.append(f"GPS fix type {state.gps_fix_type} insufficient.")
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
