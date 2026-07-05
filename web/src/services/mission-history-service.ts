import { apiDelete, apiGet, fileUrl } from '@/services/api-client'
import type {
  MissionDetail,
  MissionListResponse,
  MissionLogResponse,
} from '@/types/mission-history'

export function listMissions(query: string, signal?: AbortSignal): Promise<MissionListResponse> {
  const qs = query ? `?q=${encodeURIComponent(query)}` : ''
  return apiGet<MissionListResponse>(`/missions${qs}`, signal)
}

export function fetchMissionDetail(name: string, signal?: AbortSignal): Promise<MissionDetail> {
  return apiGet<MissionDetail>(`/missions/${encodeURIComponent(name)}`, signal)
}

export function fetchMissionLog(
  name: string,
  tail = 500,
  signal?: AbortSignal,
): Promise<MissionLogResponse> {
  return apiGet<MissionLogResponse>(
    `/missions/${encodeURIComponent(name)}/log?tail=${tail}`,
    signal,
  )
}

export function deleteMission(name: string): Promise<{ success: boolean; message: string }> {
  return apiDelete(`/missions/${encodeURIComponent(name)}`)
}

export function missionDownloadUrl(name: string): string {
  return fileUrl(`/missions/${encodeURIComponent(name)}/download`)
}

export function missionImageUrl(missionName: string, relativeFilename: string): string {
  return fileUrl(`/missions-data/${encodeURIComponent(missionName)}/${relativeFilename}`)
}

/** Thumbnail for a captured image — filename is "images/photo_00001.jpg";
 * the thumbnail sibling lives at "images/thumbs/photo_00001_thumb.jpg"
 * (see server/services/storage_service.py:MissionStorage.thumb_path_for). */
export function missionThumbnailUrl(missionName: string, relativeFilename: string): string {
  const base = relativeFilename.split('/').pop() ?? relativeFilename
  const thumbName = `${base.replace(/\.[^.]+$/, '')}_thumb.jpg`
  return fileUrl(`/missions-data/${encodeURIComponent(missionName)}/images/thumbs/${thumbName}`)
}
