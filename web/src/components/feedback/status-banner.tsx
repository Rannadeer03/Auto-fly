import type { ReactNode } from 'react'
import { AlertTriangle, CameraOff, SatelliteDish, WifiOff } from 'lucide-react'
import { useConnectionStatus } from '@/hooks/use-connection-status'
import { useUiStore } from '@/store/ui-store'

/** Slim, always-on-top banner for conditions that block or degrade mission
 * planning/execution. Only the single highest-priority condition shows at
 * once — silent when everything is nominal. */
export function StatusBanner() {
  const status = useConnectionStatus()
  const section = useUiStore((s) => s.activeSection)

  if (!status.backendOnline) {
    return (
      <Banner tone="danger" icon={<WifiOff className="h-4 w-4" />}>
        Backend unreachable — check that the drone computer is powered on and reachable on the
        network.
      </Banner>
    )
  }

  if (section === 'mission' && !status.droneConnected) {
    return (
      <Banner tone="warning" icon={<AlertTriangle className="h-4 w-4" />}>
        Drone not connected — you can still plan and preview a survey, but upload and execution
        need a Pixhawk link.
      </Banner>
    )
  }

  if (status.droneConnected && !status.gpsOk && (section === 'mission' || section === 'drone-status')) {
    return (
      <Banner tone="warning" icon={<SatelliteDish className="h-4 w-4" />}>
        GPS fix unavailable — a 3D fix is required before arming and flying a survey.
      </Banner>
    )
  }

  if (!status.cameraHealthy && (section === 'camera' || section === 'mission')) {
    return (
      <Banner tone="warning" icon={<CameraOff className="h-4 w-4" />}>
        Camera disconnected — waypoint captures will fail until the USB camera reconnects.
      </Banner>
    )
  }

  return null
}

function Banner({
  tone,
  icon,
  children,
}: {
  tone: 'danger' | 'warning'
  icon: ReactNode
  children: ReactNode
}) {
  return (
    <div
      className={
        tone === 'danger'
          ? 'flex items-center gap-2 border-b border-danger-600/40 bg-danger-600/15 px-4 py-1.5 text-xs font-medium text-danger-500'
          : 'flex items-center gap-2 border-b border-warning-500/30 bg-warning-500/10 px-4 py-1.5 text-xs font-medium text-warning-500'
      }
    >
      {icon}
      {children}
    </div>
  )
}
