import { useMemo } from 'react'
import { useHealth } from '@/hooks/use-health'
import { useTelemetry } from '@/hooks/use-telemetry'

export type LinkLevel = 'ok' | 'degraded' | 'down'

export interface ConnectionStatus {
  backendOnline: boolean
  droneConnected: boolean
  gpsOk: boolean
  cameraHealthy: boolean
  linkLevel: LinkLevel
}

/** Aggregates health + telemetry polls into the status the whole app reacts to. */
export function useConnectionStatus(): ConnectionStatus {
  const health = useHealth()
  const telemetry = useTelemetry()

  return useMemo(() => {
    const backendOnline = health.isSuccess && !health.isError
    const droneConnected = Boolean(telemetry.data?.connected)
    const gpsOk = Boolean(telemetry.data?.health.gps_ok)
    const cameraHealthy = Boolean(health.data?.camera_healthy)

    let linkLevel: LinkLevel = 'down'
    if (backendOnline && droneConnected) {
      const ago = telemetry.data?.last_heartbeat_ago_s ?? 99
      linkLevel = ago < 3 ? 'ok' : 'degraded'
    } else if (backendOnline) {
      linkLevel = 'degraded'
    }

    return { backendOnline, droneConnected, gpsOk, cameraHealthy, linkLevel }
  }, [health.isSuccess, health.isError, health.data, telemetry.data])
}
