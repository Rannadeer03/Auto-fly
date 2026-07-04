import { apiGet, apiPost } from '@/services/api-client'
import type { ApiResponse } from '@/types/mission'
import type { PortsResponse, HealthResponse } from '@/types/system'

export function fetchPorts(): Promise<PortsResponse> {
  return apiGet<PortsResponse>('/ports')
}

export function connectDrone(): Promise<ApiResponse> {
  return apiPost<ApiResponse>('/connect')
}

export function disconnectDrone(): Promise<ApiResponse> {
  return apiPost<ApiResponse>('/disconnect')
}

export function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return apiGet<HealthResponse>('/health', signal)
}
