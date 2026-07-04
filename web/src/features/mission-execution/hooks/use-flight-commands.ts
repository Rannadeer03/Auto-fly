import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { sendCommand, type FlightCommand } from '@/services/command-service'
import { connectDrone, disconnectDrone } from '@/services/connection-service'

const COMMAND_LABELS: Record<FlightCommand, string> = {
  arm: 'Arm',
  disarm: 'Disarm',
  start: 'Start mission',
  pause: 'Pause (Loiter)',
  resume: 'Resume',
  rtl: 'Return to Launch',
  land: 'Land',
  emergency_stop: 'Emergency stop',
}

/** One mutation per flight command — success/failure surfaces as a toast,
 * and telemetry/mission-session queries refresh immediately after. */
export function useFlightCommand(command: FlightCommand) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => sendCommand(command),
    onSuccess: (res) => {
      if (res.success) {
        toast.success(res.message || `${COMMAND_LABELS[command]} succeeded`)
      } else {
        toast.error(res.message || `${COMMAND_LABELS[command]} rejected`)
      }
      queryClient.invalidateQueries({ queryKey: ['telemetry'] })
      queryClient.invalidateQueries({ queryKey: ['mission-session'] })
    },
    onError: (err: Error) => {
      toast.error(`${COMMAND_LABELS[command]} failed — ${err.message}`)
    },
  })
}

export function useConnectDrone() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: connectDrone,
    onSuccess: (res) => {
      if (res.success) toast.success(res.message)
      else toast.error(res.message)
      queryClient.invalidateQueries({ queryKey: ['telemetry'] })
      queryClient.invalidateQueries({ queryKey: ['health'] })
    },
    onError: (err: Error) => toast.error(`Connect failed — ${err.message}`),
  })
}

export function useDisconnectDrone() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: disconnectDrone,
    onSuccess: (res) => {
      if (res.success) toast.success(res.message)
      else toast.error(res.message)
      queryClient.invalidateQueries({ queryKey: ['telemetry'] })
      queryClient.invalidateQueries({ queryKey: ['health'] })
    },
    onError: (err: Error) => toast.error(`Disconnect failed — ${err.message}`),
  })
}
