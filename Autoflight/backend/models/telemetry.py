"""Pydantic models for telemetry data returned by GET /telemetry."""
from pydantic import BaseModel


class GPSData(BaseModel):
    satellites_visible: int = 0
    fix_type: int = 0
    fix_type_str: str = "No GPS"
    hdop: float = 99.99
    vdop: float = 99.99
    latitude: float = 0.0
    longitude: float = 0.0
    altitude_msl: float = 0.0


class AttitudeData(BaseModel):
    roll_deg: float = 0.0
    pitch_deg: float = 0.0
    yaw_deg: float = 0.0
    roll_speed_dps: float = 0.0
    pitch_speed_dps: float = 0.0
    yaw_speed_dps: float = 0.0


class BatteryData(BaseModel):
    voltage: float = 0.0
    current: float = 0.0
    remaining_percent: int = -1
    consumed_mah: float = 0.0


class PositionData(BaseModel):
    latitude: float = 0.0
    longitude: float = 0.0
    altitude_msl: float = 0.0
    altitude_rel: float = 0.0
    ground_speed: float = 0.0
    air_speed: float = 0.0
    heading: int = 0
    climb_rate: float = 0.0


class MissionTelemetry(BaseModel):
    current_waypoint: int = 0
    total_waypoints: int = 0
    distance_to_waypoint_m: float = 0.0
    progress_percent: float = 0.0


class HealthData(BaseModel):
    ekf_ok: bool = False
    gps_ok: bool = False
    battery_ok: bool = False
    gyro_ok: bool = False
    accelerometer_ok: bool = False
    barometer_ok: bool = False
    compass_ok: bool = False


class TelemetryData(BaseModel):
    connected: bool = False
    armed: bool = False
    flight_mode: str = "UNKNOWN"
    system_status: str = "UNINIT"
    last_heartbeat_ago_s: float = 99.0
    mission_uploaded: bool = False
    link_quality_percent: float = 0.0

    gps: GPSData = GPSData()
    attitude: AttitudeData = AttitudeData()
    battery: BatteryData = BatteryData()
    position: PositionData = PositionData()
    mission: MissionTelemetry = MissionTelemetry()
    health: HealthData = HealthData()
