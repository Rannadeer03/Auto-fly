"""
Telemetry snapshot builder.

Reads from the shared DroneState (populated by the MAVLink receiver thread)
and constructs the Pydantic TelemetryData model returned to the frontend.
"""
import time
from types import SimpleNamespace

from mavlink.connection import drone_state, MAV_STATE_NAMES, GPS_FIX_NAMES
from models.telemetry import (
    TelemetryData,
    GPSData,
    AttitudeData,
    BatteryData,
    PositionData,
    MissionTelemetry,
    HealthData,
)


def _link_quality(ago_s: float) -> float:
    """Estimate link quality from heartbeat recency."""
    if ago_s < 1.0:
        return 100.0
    if ago_s < 2.0:
        return 80.0
    if ago_s < 3.0:
        return 50.0
    if ago_s < 5.0:
        return 20.0
    return 0.0


class TelemetryReader:
    """Builds a TelemetryData snapshot from the current DroneState."""

    @staticmethod
    def snapshot() -> TelemetryData:
        # Read every field through the DroneState lock in one pass so a
        # concurrent MAVLink update can't be applied halfway through this
        # snapshot (e.g. lat updated but lon still from the previous fix).
        s = SimpleNamespace(**drone_state.snapshot())
        ago = 99.0 if s.last_heartbeat_time == 0.0 else time.monotonic() - s.last_heartbeat_time

        return TelemetryData(
            connected=s.connected,
            armed=s.armed,
            flight_mode=s.flight_mode,
            system_status=MAV_STATE_NAMES.get(s.system_status, "UNKNOWN"),
            last_heartbeat_ago_s=round(ago, 1),
            mission_uploaded=s.mission_uploaded,
            link_quality_percent=_link_quality(ago),

            gps=GPSData(
                satellites_visible=s.gps_satellites,
                fix_type=s.gps_fix_type,
                fix_type_str=GPS_FIX_NAMES.get(s.gps_fix_type, "Unknown"),
                hdop=round(s.gps_hdop, 2),
                vdop=round(s.gps_vdop, 2),
                latitude=s.latitude,
                longitude=s.longitude,
                altitude_msl=round(s.altitude_msl, 2),
            ),

            attitude=AttitudeData(
                roll_deg=round(s.roll, 2),
                pitch_deg=round(s.pitch, 2),
                yaw_deg=round(s.yaw, 2),
                roll_speed_dps=round(s.roll_speed, 2),
                pitch_speed_dps=round(s.pitch_speed, 2),
                yaw_speed_dps=round(s.yaw_speed, 2),
            ),

            battery=BatteryData(
                voltage=round(s.battery_voltage, 2),
                current=round(s.battery_current, 2),
                remaining_percent=s.battery_remaining,
                consumed_mah=round(s.battery_consumed_mah, 1),
            ),

            position=PositionData(
                latitude=s.latitude,
                longitude=s.longitude,
                altitude_msl=round(s.altitude_msl, 2),
                altitude_rel=round(s.altitude_rel, 2),
                ground_speed=round(s.ground_speed, 2),
                air_speed=round(s.air_speed, 2),
                heading=s.heading,
                climb_rate=round(s.climb_rate, 2),
            ),

            mission=MissionTelemetry(
                current_waypoint=s.current_waypoint,
                total_waypoints=s.waypoint_count,
                distance_to_waypoint_m=round(s.distance_to_waypoint, 1),
                progress_percent=round(
                    (s.current_waypoint / s.waypoint_count * 100)
                    if s.waypoint_count > 0
                    else 0.0,
                    1,
                ),
            ),

            health=HealthData(
                ekf_ok=s.ekf_ok,
                gps_ok=s.gps_fix_type >= 3,
                battery_ok=(s.battery_remaining > 20 or s.battery_remaining == -1),
                gyro_ok=s.gyro_ok,
                accelerometer_ok=s.accel_ok,
                barometer_ok=s.baro_ok,
                compass_ok=s.compass_ok,
            ),
        )
