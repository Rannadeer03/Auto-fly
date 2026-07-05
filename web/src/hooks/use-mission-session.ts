import { useQuery } from '@tanstack/react-query'
import { MISSION_SESSION_POLL_MS } from '@/constants/api'
import { fetchMissionSession, fetchMissionStatus } from '@/services/mission-service'

export function useMissionSession() {
  return useQuery({
    queryKey: ['mission-session'],
    queryFn: ({ signal }) => fetchMissionSession(signal),
    refetchInterval: MISSION_SESSION_POLL_MS,
    retry: false,
  })
}

export function useMissionStatus() {
  return useQuery({
    queryKey: ['mission-status'],
    queryFn: ({ signal }) => fetchMissionStatus(signal),
    refetchInterval: MISSION_SESSION_POLL_MS,
    retry: false,
  })
}
