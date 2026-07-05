import type { ReactNode } from 'react'
import { cn } from '@/utils/cn'

interface StatTileProps {
  label: string
  value: string
  icon?: ReactNode
  tone?: 'default' | 'warning' | 'accent'
  className?: string
}

export function StatTile({ label, value, icon, tone = 'default', className }: StatTileProps) {
  return (
    <div className={cn('rounded-[var(--radius-control)] bg-surface-3 px-3 py-2.5', className)}>
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-text-tertiary">
        {icon}
        {label}
      </div>
      <div
        className={cn(
          'mt-1 font-mono text-base font-semibold',
          tone === 'warning' && 'text-warning-500',
          tone === 'accent' && 'text-accent-400',
          tone === 'default' && 'text-text-primary',
        )}
      >
        {value}
      </div>
    </div>
  )
}
