// Mirrors server/models/telemetry.py — keep field names identical to the
// backend response so the API layer needs no translation.

export interface GPSData {
  satellites_visible: number
  fix_type: number
  fix_type_str: string
  hdop: number
  vdop: number
  latitude: number
  longitude: number
  altitude_msl: number
}

export interface AttitudeData {
  roll_deg: number
  pitch_deg: number
  yaw_deg: number
  roll_speed_dps: number
  pitch_speed_dps: number
  yaw_speed_dps: number
}

export interface BatteryData {
  voltage: number
  current: number
  remaining_percent: number
  consumed_mah: number
}

export interface PositionData {
  latitude: number
  longitude: number
  altitude_msl: number
  altitude_rel: number
  ground_speed: number
  air_speed: number
  heading: number
  climb_rate: number
}

export interface MissionTelemetry {
  current_waypoint: number
  total_waypoints: number
  distance_to_waypoint_m: number
  progress_percent: number
}

export interface HealthData {
  ekf_ok: boolean
  gps_ok: boolean
  battery_ok: boolean
  gyro_ok: boolean
  accelerometer_ok: boolean
  barometer_ok: boolean
  compass_ok: boolean
}

export interface TelemetryData {
  connected: boolean
  armed: boolean
  flight_mode: string
  system_status: string
  last_heartbeat_ago_s: number
  mission_uploaded: boolean
  link_quality_percent: number
  gps: GPSData
  attitude: AttitudeData
  battery: BatteryData
  position: PositionData
  mission: MissionTelemetry
  health: HealthData
}
