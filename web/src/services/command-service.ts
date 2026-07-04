import { apiPost } from '@/services/api-client'
import type { ApiResponse } from '@/types/mission'

// Every flight command maps 1:1 to a POST route in server/api/commands.py.
export type FlightCommand =
  | 'arm'
  | 'disarm'
  | 'start'
  | 'pause'
  | 'resume'
  | 'rtl'
  | 'land'
  | 'emergency_stop'

export function sendCommand(command: FlightCommand): Promise<ApiResponse> {
  return apiPost<ApiResponse>(`/${command}`)
}
