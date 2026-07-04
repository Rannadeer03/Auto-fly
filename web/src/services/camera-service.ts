import { apiGet, apiPost, fileUrl } from '@/services/api-client'
import type { ApiResponse } from '@/types/mission'
import type { CameraStatusResponse } from '@/types/system'

export function fetchCameraStatus(signal?: AbortSignal): Promise<CameraStatusResponse> {
  return apiGet<CameraStatusResponse>('/camera/status', signal)
}

export function capturePhoto(): Promise<ApiResponse> {
  return apiPost<ApiResponse>('/camera/photo')
}

export function startRecording(): Promise<ApiResponse> {
  return apiPost<ApiResponse>('/camera/recording/start')
}

export function stopRecording(): Promise<ApiResponse> {
  return apiPost<ApiResponse>('/camera/recording/stop')
}

/** POST /camera/photo returns the server's absolute filesystem path; manual
 * captures always land in <MISSIONS_DIR>/captures (services/camera_service.py),
 * which is mounted at /missions-data — so the basename is enough to build a URL. */
export function captureFileUrl(serverPath: string): string {
  const basename = serverPath.split('/').pop()
  return fileUrl(`/missions-data/captures/${basename}`)
}
