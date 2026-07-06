// Mirrors server/services/mission_library_service.py and server/api/mission_library.py
import type { CaptureMode, GridResponse, Mission, PlanInfo } from '@/types/mission'

export type LibraryMode = 'survey' | 'manual'

export interface SurveyLibraryParams {
  altitude_m: number
  speed_ms: number
  side_overlap_pct: number
  front_overlap_pct: number
  angle_deg: number
  capture_mode: CaptureMode
  hold_time_s: number
  camera_angle_deg: number
}

export interface ManualLibraryParams {
  speed_ms: number
}

export type LibraryParams = SurveyLibraryParams | ManualLibraryParams

export interface ManualLibraryWaypoint {
  lat: number
  lon: number
  altitude_m: number
}

export interface LibrarySummary {
  id: string
  name: string
  description: string
  created_at: string
  updated_at: string
  mode: LibraryMode
  waypoint_count: number
  total_distance_km: number
  estimated_duration_minutes: number
  estimated_battery_percent: number
  params: LibraryParams
}

export interface LibraryEntry extends LibrarySummary {
  // Survey-only
  polygon?: [number, number][]
  // Manual-only
  launch?: [number, number]
  home?: [number, number]
  manual_waypoints?: ManualLibraryWaypoint[]
  mission: Mission
  plan_info: PlanInfo | null
}

export interface LibraryListResponse {
  entries: LibrarySummary[]
  count: number
  query: string
}

export interface SaveToLibraryRequest {
  name: string
  description: string
  polygon: [number, number][]
  altitude_m: number
  speed_ms: number
  side_overlap_pct: number
  front_overlap_pct: number
  angle_deg: number
  capture_mode?: CaptureMode
  hold_time_s?: number
  camera_angle_deg?: number
}

export interface ManualSaveToLibraryRequest {
  name: string
  description: string
  launch: [number, number]
  home: [number, number]
  waypoints: ManualLibraryWaypoint[]
  speed_ms: number
}

export interface SaveToLibraryResponse {
  success: boolean
  message: string
  entry: LibraryEntry
}

export interface DeployLibraryResponse extends GridResponse {
  mode: LibraryMode
  polygon?: [number, number][] | null
  params?: LibraryParams | null
  launch?: [number, number] | null
  home?: [number, number] | null
  manual_waypoints?: ManualLibraryWaypoint[] | null
}
