import type { ComponentProps } from 'react'
import * as SwitchPrimitive from '@radix-ui/react-switch'
import { cn } from '@/utils/cn'

export function Switch({
  className,
  ...props
}: ComponentProps<typeof SwitchPrimitive.Root>) {
  return (
    <SwitchPrimitive.Root
      className={cn(
        'peer inline-flex h-5 w-9 shrink-0 items-center rounded-full border border-border bg-surface-3 transition-colors',
        'data-[state=checked]:bg-accent-500 data-[state=checked]:border-accent-500',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500/50',
        className,
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb className="pointer-events-none block h-3.5 w-3.5 translate-x-0.5 rounded-full bg-text-primary shadow transition-transform data-[state=checked]:translate-x-4 data-[state=checked]:bg-canvas" />
    </SwitchPrimitive.Root>
  )
}
