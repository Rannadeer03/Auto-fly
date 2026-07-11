import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { MISSION_LIST_POLL_MS } from '@/constants/api'
import {
  deleteMission,
  fetchMissionDetail,
  fetchMissionLog,
  listMissions,
} from '@/services/mission-history-service'

export function useMissionList(query: string) {
  return useQuery({
    queryKey: ['missions', query],
    queryFn: ({ signal }) => listMissions(query, signal),
    staleTime: 5000,
    // Mission folders are created/finalised entirely server-side (a flight
    // completing, possibly triggered by RC/QGroundControl, not this UI), so
    // there's no frontend mutation to invalidate this list on — poll it
    // instead, and catch up immediately when the tab regains focus.
    refetchInterval: MISSION_LIST_POLL_MS,
    refetchOnWindowFocus: true,
  })
}

export function useMissionDetail(name: string | null) {
  return useQuery({
    queryKey: ['mission-detail', name],
    queryFn: ({ signal }) => fetchMissionDetail(name as string, signal),
    enabled: name !== null,
  })
}

export function useMissionLog(name: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ['mission-log', name],
    queryFn: ({ signal }) => fetchMissionLog(name as string, 500, signal),
    enabled: name !== null && enabled,
  })
}

export function useDeleteMission() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: deleteMission,
    onSuccess: (res) => {
      if (res.success) toast.success(res.message)
      else toast.error(res.message)
      queryClient.invalidateQueries({ queryKey: ['missions'] })
    },
    onError: (err: Error) => toast.error(`Delete failed — ${err.message}`),
  })
}
