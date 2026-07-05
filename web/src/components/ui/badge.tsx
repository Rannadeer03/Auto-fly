import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/utils/cn'

const badgeVariants = cva(
  'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium leading-none',
  {
    variants: {
      variant: {
        neutral: 'bg-surface-3 text-text-secondary',
        success: 'bg-success-500/15 text-success-500',
        warning: 'bg-warning-500/15 text-warning-500',
        danger: 'bg-danger-500/15 text-danger-500',
        info: 'bg-info-500/15 text-info-500',
        accent: 'bg-accent-500/15 text-accent-400',
      },
    },
    defaultVariants: { variant: 'neutral' },
  },
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {
  dot?: boolean
}

export function Badge({ className, variant, dot, children, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ variant, className }))} {...props}>
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current" />}
      {children}
    </span>
  )
}
