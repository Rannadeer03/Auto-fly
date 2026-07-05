// Mirrors misc. endpoints: /health, /camera/status, /ports, /logs

export interface HealthResponse {
  status: string
  version: string
  drone_connected: boolean
  mavlink_port: string
  camera_healthy: boolean
  recording: boolean
  mission_session_active: boolean
}

export interface CameraStats {
  healthy: boolean
  device: string
  available_devices: string[]
  measured_fps: number
  frame_count: number
  configured_width: number
  configured_height: number
  configured_fps: number
  last_frame_age_seconds: number | null
}

export interface RecordingStatus {
  recording: boolean
  path?: string | null
  duration_s?: number
}

export interface CameraStatusResponse {
  camera: CameraStats
  recording: RecordingStatus
}

export interface PortsResponse {
  ports: string[]
  count: number
  hint?: string
  error?: string
}

export interface LogsResponse {
  logs: string[]
}
