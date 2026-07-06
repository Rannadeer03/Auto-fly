// Mirrors server/services/mission_library_service.py and server/api/mission_library.py
import type { CaptureMode, GridResponse, ManualItemInput, Mission, PlanInfo } from '@/types/mission'

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
  acceptance_radius_m?: number
  takeoff_speed_ms?: number
  climb_speed_ms?: number
  descent_speed_ms?: number
  rtl_speed_ms?: number
  land_speed_ms?: number
  camera_trigger_distance_m?: number
}

export type LibraryParams = SurveyLibraryParams | ManualLibraryParams

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
  home?: [number, number]
  manual_items?: ManualItemInput[]
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
  home: [number, number]
  items: ManualItemInput[]
  speed_ms: number
  acceptance_radius_m?: number
  extra_settings?: Record<string, number>
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
  home?: [number, number] | null
  manual_items?: ManualItemInput[] | null
}
