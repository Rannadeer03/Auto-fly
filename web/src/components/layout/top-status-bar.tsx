import type { ReactNode } from 'react'
import { Battery, BatteryWarning, Satellite, Signal, SignalHigh, SignalLow } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { CommandBar } from '@/features/mission-execution/components/command-bar'
import { useTelemetry } from '@/hooks/use-telemetry'
import { useConnectionStatus } from '@/hooks/use-connection-status'
import { FLIGHT_MODE_LABELS } from '@/constants/mavlink'
import { cn } from '@/utils/cn'

export function TopStatusBar() {
  const { data: t } = useTelemetry()
  const status = useConnectionStatus()

  const battery = t?.battery.remaining_percent ?? -1
  const batteryLow = battery >= 0 && battery < 20

  return (
    <header className="flex h-14 shrink-0 items-center justify-between gap-4 border-b border-border bg-surface px-4">
      <div className="flex items-center gap-3">
        <LinkBadge level={status.linkLevel} />
        <Badge variant={t?.armed ? 'danger' : 'neutral'} dot>
          {t?.armed ? 'ARMED' : 'DISARMED'}
        </Badge>
        <Badge variant="accent">{FLIGHT_MODE_LABELS[t?.flight_mode ?? 'UNKNOWN'] ?? t?.flight_mode}</Badge>
      </div>

      <div className="flex items-center gap-4">
        <Stat
          icon={<Satellite className="h-3.5 w-3.5" />}
          label={`${t?.gps.satellites_visible ?? 0} sats`}
          warn={!status.gpsOk}
        />
        <Stat
          icon={
            batteryLow ? (
              <BatteryWarning className="h-3.5 w-3.5" />
            ) : (
              <Battery className="h-3.5 w-3.5" />
            )
          }
          label={battery >= 0 ? `${battery}%` : '—'}
          warn={batteryLow}
        />
      </div>

      <CommandBar />
    </header>
  )
}

function LinkBadge({ level }: { level: 'ok' | 'degraded' | 'down' }) {
  if (level === 'ok')
    return (
      <Badge variant="success" dot>
        <SignalHigh className="h-3 w-3" /> Link OK
      </Badge>
    )
  if (level === 'degraded')
    return (
      <Badge variant="warning" dot>
        <Signal className="h-3 w-3" /> Degraded
      </Badge>
    )
  return (
    <Badge variant="danger" dot>
      <SignalLow className="h-3 w-3" /> No Link
    </Badge>
  )
}

function Stat({
  icon,
  label,
  warn,
}: {
  icon: ReactNode
  label: string
  warn?: boolean
}) {
  return (
    <div
      className={cn(
        'flex items-center gap-1.5 text-xs font-medium',
        warn ? 'text-warning-500' : 'text-text-secondary',
      )}
    >
      {icon}
      <span className="font-mono">{label}</span>
    </div>
  )
}
