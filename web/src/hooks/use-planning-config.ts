import { useQuery } from '@tanstack/react-query'
import { fetchPlanningConfig } from '@/services/mission-service'

export function usePlanningConfig() {
  return useQuery({
    queryKey: ['planning-config'],
    queryFn: () => fetchPlanningConfig(),
    staleTime: Infinity,
    retry: 2,
  })
}
