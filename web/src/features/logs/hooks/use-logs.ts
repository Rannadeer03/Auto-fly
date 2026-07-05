import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { LOGS_POLL_MS } from '@/constants/api'
import { clearLogs, fetchLogs } from '@/services/logs-service'

export function useLogs(enabled: boolean) {
  return useQuery({
    queryKey: ['logs'],
    queryFn: ({ signal }) => fetchLogs(200, signal),
    refetchInterval: enabled ? LOGS_POLL_MS : false,
  })
}

export function useClearLogs() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: clearLogs,
    onSuccess: () => {
      toast.success('Logs cleared')
      queryClient.invalidateQueries({ queryKey: ['logs'] })
    },
  })
}
