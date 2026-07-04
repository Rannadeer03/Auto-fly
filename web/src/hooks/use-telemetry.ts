import { useQuery } from '@tanstack/react-query'
import { TELEMETRY_POLL_MS } from '@/constants/api'
import { fetchTelemetry } from '@/services/telemetry-service'

export function useTelemetry() {
  return useQuery({
    queryKey: ['telemetry'],
    queryFn: ({ signal }) => fetchTelemetry(signal),
    refetchInterval: TELEMETRY_POLL_MS,
    // Telemetry is transient — a failed poll shouldn't retry-storm the link.
    retry: false,
  })
}
