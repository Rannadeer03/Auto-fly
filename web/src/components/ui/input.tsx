import * as React from 'react'
import { cn } from '@/utils/cn'

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        'h-9 w-full rounded-[var(--radius-control)] border border-border bg-surface-2 px-3 text-sm text-text-primary placeholder:text-text-tertiary',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500/50 focus-visible:border-accent-500/50',
        'disabled:opacity-40 disabled:pointer-events-none',
        className,
      )}
      {...props}
    />
  ),
)
Input.displayName = 'Input'

export const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea
    ref={ref}
    className={cn(
      'w-full resize-none rounded-[var(--radius-control)] border border-border bg-surface-2 px-3 py-2 text-sm text-text-primary placeholder:text-text-tertiary',
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500/50 focus-visible:border-accent-500/50',
      className,
    )}
    {...props}
  />
))
Textarea.displayName = 'Textarea'
