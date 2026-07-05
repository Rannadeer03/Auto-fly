// Mirrors server/models/mission.py

export interface WaypointItem {
  index: number
  current: boolean
  frame: number
  command: number
  param1: number
  param2: number
  param3: number
  param4: number
  latitude: number
  longitude: number
  altitude: number
  autocontinue: boolean
  is_capture_point: boolean
}

export interface Mission {
  filename: string
  source_format: 'waypoints' | 'plan' | 'grid'
  waypoint_count: number
  nav_waypoints: number
  total_distance_m: number
  total_distance_km: number
  estimated_duration_minutes: number
  estimated_battery_percent: number
  min_altitude_m: number
  max_altitude_m: number
  waypoints: WaypointItem[]
}

export interface MissionStatus {
  uploaded: boolean
  waypoint_count: number
  current_waypoint: number
  total_waypoints: number
  progress_percent: number
  mission_info: Mission | null
}

export interface ApiResponse<TData = Record<string, unknown>> {
  success: boolean
  message: string
  data?: TData | null
}

export interface UploadResponse {
  success: boolean
  message: string
  mission_info: Mission | null
  uploaded_to_drone: boolean
  verified: boolean
  verification_message: string
}

export type CaptureMode = 'hover' | 'continuous'

export interface PlanInfo {
  line_count: number
  line_spacing_m: number
  photo_spacing_m: number
  footprint_width_m: number
  footprint_height_m: number
  estimated_photos: number
  capture_mode: CaptureMode
  hold_time_s: number
  capture_waypoint_count: number
  hold_time_total_s: number
  applied_photo_distance_m?: number
}

export interface GridResponse extends UploadResponse {
  plan_info: PlanInfo | null
}

export interface GridRequest {
  polygon: [number, number][]
  altitude_m: number
  speed_ms: number
  side_overlap_pct: number
  front_overlap_pct: number
  angle_deg: number
  upload: boolean
  photo_distance_m?: number
  capture_mode?: CaptureMode
  hold_time_s?: number
  mission_name?: string
  camera_angle_deg?: number
}

export interface PlanningConfig {
  altitude_m: number
  speed_ms: number
  side_overlap_pct: number
  front_overlap_pct: number
  grid_angle_deg: number
  capture_mode: CaptureMode
  hover_hold_time_s: number
  photo_capture_mode: 'distance' | 'time'
  photo_distance_m: number
  photo_interval_s: number
  recording_enabled: boolean
  camera_hfov_deg: number
  camera_vfov_deg: number
  camera_width_px: number
  camera_height_px: number
  camera_pitch_deg: number
}

export interface MissionSessionStatus {
  active: boolean
  mission_folder: string | null
  started_at: string | null
  photos_captured: number
  failed_captures: number
  recording: boolean
  capture_mode: CaptureMode
  last_completed: string | null
}
