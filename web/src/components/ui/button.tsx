import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/utils/cn'

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[var(--radius-control)] text-sm font-medium transition-colors duration-150 disabled:pointer-events-none disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500/50',
  {
    variants: {
      variant: {
        default: 'bg-surface-3 text-text-primary hover:bg-surface-3/80 border border-border',
        accent: 'bg-accent-500 text-canvas hover:bg-accent-400 font-semibold',
        ghost: 'text-text-secondary hover:text-text-primary hover:bg-surface-2',
        outline: 'border border-border text-text-primary hover:bg-surface-2',
        danger: 'bg-danger-600 text-white hover:bg-danger-500 font-semibold',
        success: 'bg-success-500/90 text-canvas hover:bg-success-500 font-semibold',
      },
      size: {
        sm: 'h-8 px-2.5 text-xs',
        default: 'h-9 px-3.5',
        lg: 'h-11 px-5 text-base',
        icon: 'h-9 w-9 shrink-0',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  },
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button'
    return (
      <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />
    )
  },
)
Button.displayName = 'Button'
