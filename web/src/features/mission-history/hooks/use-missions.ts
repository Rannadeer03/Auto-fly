import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
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
