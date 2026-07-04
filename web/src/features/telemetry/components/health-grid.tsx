import { Check, X } from 'lucide-react'
import type { HealthData } from '@/types/telemetry'
import { cn } from '@/utils/cn'

const LABELS: Record<keyof HealthData, string> = {
  ekf_ok: 'EKF',
  gps_ok: 'GPS',
  battery_ok: 'Battery',
  gyro_ok: 'Gyroscope',
  accelerometer_ok: 'Accelerometer',
  barometer_ok: 'Barometer',
  compass_ok: 'Compass',
}

export function HealthGrid({ health }: { health: HealthData }) {
  return (
    <div className="grid grid-cols-2 gap-2">
      {(Object.keys(LABELS) as (keyof HealthData)[]).map((key) => {
        const ok = health[key]
        return (
          <div
            key={key}
            className={cn(
              'flex items-center justify-between rounded-[var(--radius-control)] px-2.5 py-2 text-xs',
              ok ? 'bg-success-500/10 text-success-500' : 'bg-danger-500/10 text-danger-500',
            )}
          >
            <span className="text-text-secondary">{LABELS[key]}</span>
            {ok ? <Check className="h-3.5 w-3.5" /> : <X className="h-3.5 w-3.5" />}
          </div>
        )
      })}
    </div>
  )
}
