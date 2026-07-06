import type { ReactNode } from 'react'
import { LocateFixed, Crosshair } from 'lucide-react'
import { useMapInstance } from '@/features/map/map-context'
import { useGeolocationStore } from '@/store/geolocation-store'
import { useTelemetry } from '@/hooks/use-telemetry'
import { cn } from '@/utils/cn'

/** "Center on My Location" / "Center on Drone" — pure map.flyTo calls, never
 * triggered automatically, so they never fight with manual panning. */
export function CenterControls() {
  const map = useMapInstance()
  const myPosition = useGeolocationStore((s) => s.position)
  const { data: telemetry } = useTelemetry()

  const dronePosition =
    telemetry?.connected && (telemetry.position.latitude || telemetry.position.longitude)
      ? telemetry.position
      : null

  const centerOnMyLocation = () => {
    if (!map || !myPosition) return
    map.flyTo({ center: [myPosition.lng, myPosition.lat] })
  }

  const centerOnDrone = () => {
    if (!map || !dronePosition) return
    map.flyTo({ center: [dronePosition.longitude, dronePosition.latitude] })
  }

  return (
    <div className="glass-panel flex items-center gap-0.5 rounded-[var(--radius-control)] p-1">
      <ControlButton
        disabled={!myPosition}
        onClick={centerOnMyLocation}
        label="Center on My Location"
        icon={<LocateFixed className="h-4 w-4" />}
      />
      <ControlButton
        disabled={!dronePosition}
        onClick={centerOnDrone}
        label="Center on Drone"
        icon={<Crosshair className="h-4 w-4" />}
      />
    </div>
  )
}

function ControlButton({
  disabled,
  onClick,
  label,
  icon,
}: {
  disabled?: boolean
  onClick: () => void
  label: string
  icon: ReactNode
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={label}
      aria-label={label}
      className={cn(
        'flex h-8 w-8 items-center justify-center rounded-[6px] transition-colors',
        disabled
          ? 'cursor-not-allowed text-text-tertiary/40'
          : 'text-text-secondary hover:bg-surface-3 hover:text-text-primary',
      )}
    >
      {icon}
    </button>
  )
}
