import { useQuery } from '@tanstack/react-query'
import { HEALTH_POLL_MS } from '@/constants/api'
import { fetchHealth } from '@/services/connection-service'

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: ({ signal }) => fetchHealth(signal),
    refetchInterval: HEALTH_POLL_MS,
    retry: false,
  })
}
