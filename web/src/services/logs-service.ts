import { apiDelete, apiGet } from '@/services/api-client'
import type { LogsResponse } from '@/types/system'

export function fetchLogs(count = 200, signal?: AbortSignal): Promise<LogsResponse> {
  return apiGet<LogsResponse>(`/logs?count=${count}`, signal)
}

export function clearLogs(): Promise<{ status: string }> {
  return apiDelete('/logs')
}
