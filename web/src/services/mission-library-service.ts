import { apiDelete, apiGet, apiPatch, apiPost, fileUrl } from '@/services/api-client'
import type {
  DeployLibraryResponse,
  LibraryEntry,
  LibraryListResponse,
  ManualSaveToLibraryRequest,
  SaveToLibraryRequest,
  SaveToLibraryResponse,
} from '@/types/mission-library'

export function saveToLibrary(body: SaveToLibraryRequest): Promise<SaveToLibraryResponse> {
  return apiPost<SaveToLibraryResponse>('/mission-library', body)
}

export function saveManualToLibrary(body: ManualSaveToLibraryRequest): Promise<SaveToLibraryResponse> {
  return apiPost<SaveToLibraryResponse>('/mission-library/manual', body)
}

export function listLibrary(query: string, signal?: AbortSignal): Promise<LibraryListResponse> {
  const qs = query ? `?q=${encodeURIComponent(query)}` : ''
  return apiGet<LibraryListResponse>(`/mission-library${qs}`, signal)
}

export function fetchLibraryEntry(id: string, signal?: AbortSignal): Promise<LibraryEntry> {
  return apiGet<LibraryEntry>(`/mission-library/${encodeURIComponent(id)}`, signal)
}

export function renameLibraryEntry(
  id: string,
  patch: { name?: string; description?: string },
): Promise<LibraryEntry> {
  return apiPatch<LibraryEntry>(`/mission-library/${encodeURIComponent(id)}`, patch)
}

export function duplicateLibraryEntry(id: string, name?: string): Promise<LibraryEntry> {
  return apiPost<LibraryEntry>(`/mission-library/${encodeURIComponent(id)}/duplicate`, { name })
}

export function deleteLibraryEntry(id: string): Promise<{ success: boolean; message: string; id: string }> {
  return apiDelete(`/mission-library/${encodeURIComponent(id)}`)
}

export function deployLibraryEntry(id: string): Promise<DeployLibraryResponse> {
  return apiPost<DeployLibraryResponse>(`/mission-library/${encodeURIComponent(id)}/deploy`)
}

export function libraryDownloadUrl(id: string): string {
  return fileUrl(`/mission-library/${encodeURIComponent(id)}/download`)
}
