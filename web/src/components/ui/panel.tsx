import * as React from 'react'
import { cn } from '@/utils/cn'

export function Panel({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'glass-panel rounded-[var(--radius-panel)] shadow-[0_8px_32px_rgba(0,0,0,0.35)]',
        className,
      )}
      {...props}
    />
  )
}

export function PanelHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'flex items-center justify-between border-b border-border px-4 py-3',
        className,
      )}
      {...props}
    />
  )
}

export function PanelTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3
      className={cn(
        'text-xs font-semibold uppercase tracking-wider text-text-secondary',
        className,
      )}
      {...props}
    />
  )
}

export function PanelBody({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('p-4', className)} {...props} />
}
