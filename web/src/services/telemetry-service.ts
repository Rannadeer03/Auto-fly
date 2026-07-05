import { apiGet } from '@/services/api-client'
import type { TelemetryData } from '@/types/telemetry'

export function fetchTelemetry(signal?: AbortSignal): Promise<TelemetryData> {
  return apiGet<TelemetryData>('/telemetry', signal)
}
