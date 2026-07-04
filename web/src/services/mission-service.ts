import { apiGet, apiPost, apiUploadFile } from '@/services/api-client'
import type {
  ApiResponse,
  GridRequest,
  GridResponse,
  MissionSessionStatus,
  MissionStatus,
  PlanningConfig,
  UploadResponse,
} from '@/types/mission'

export function generateSurveyMission(
  body: GridRequest,
  signal?: AbortSignal,
): Promise<GridResponse> {
  return apiPost<GridResponse>('/mission/generate', body, signal)
}

export function fetchMissionStatus(signal?: AbortSignal): Promise<MissionStatus> {
  return apiGet<MissionStatus>('/mission', signal)
}

export function clearMission(): Promise<ApiResponse> {
  return apiPost<ApiResponse>('/clear')
}

export function uploadMissionFile(file: File): Promise<UploadResponse> {
  return apiUploadFile<UploadResponse>('/upload', file)
}

export function fetchPlanningConfig(): Promise<PlanningConfig> {
  return apiGet<PlanningConfig>('/config')
}

export function fetchMissionSession(signal?: AbortSignal): Promise<MissionSessionStatus> {
  return apiGet<MissionSessionStatus>('/mission/session', signal)
}
