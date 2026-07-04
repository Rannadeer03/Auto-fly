// Mirrors the dicts returned by server/services/storage_service.py

export interface MissionMetadata {
  mission_name: string
  mission_id: string
  folder: string
  started_at: string
  ended_at: string
  end_reason: string
  waypoints_total: number
  photos_captured: number
  failed_captures: number
  video_file: string | null
  capture_mode: string
  hover_hold_time_s?: number
  camera_orientation_deg?: number
  photo_distance_m: number
  photo_interval_s: number
  recording_enabled: boolean
}

export interface FlightStats {
  samples: number
  distance_m: number
  max_altitude_rel_m: number
  max_ground_speed_ms: number
  battery_voltage_start: number | null
  battery_voltage_end: number | null
}

export interface MissionSummary {
  name: string
  mission_id: string
  has_video: boolean
  photo_count: number
  has_log: boolean
  metadata: MissionMetadata | null
  total_size_bytes: number
  stats: FlightStats | null
  active: boolean
}

export interface MissionFileEntry {
  path: string
  size: number
}

// One entry per captured image — see
// server/services/storage_service.py:IMAGE_METADATA_FIELDS for the
// authoritative field list this mirrors.
export interface ImageMetadata {
  filename: string
  mission_name: string
  mission_id: string
  timestamp: string
  latitude: number
  longitude: number
  altitude_rel: number
  altitude_msl: number
  heading_deg: number
  pitch_deg: number
  roll_deg: number
  camera_orientation_deg: number
  waypoint_number: number
  capture_sequence: number
  drone_speed_ms: number
  gps_fix_quality: string
  satellites_visible: number
}

export interface MissionDetail extends MissionSummary {
  images: ImageMetadata[] | null
  mission: Record<string, unknown> | null
  files: MissionFileEntry[]
}

export interface MissionListResponse {
  missions: MissionSummary[]
  count: number
  query: string
}

export interface MissionLogResponse {
  name: string
  lines: string[]
  total_lines: number
}
