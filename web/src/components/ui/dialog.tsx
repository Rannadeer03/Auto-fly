import * as React from 'react'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import { cn } from '@/utils/cn'

export const Dialog = DialogPrimitive.Root
export const DialogTrigger = DialogPrimitive.Trigger

export function DialogContent({
  className,
  children,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Content>) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm" />
      <DialogPrimitive.Content
        className={cn(
          'fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2',
          'glass-panel rounded-[var(--radius-panel)] p-5 shadow-2xl',
          className,
        )}
        {...props}
      >
        {children}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  )
}

export const DialogTitle = ({
  className,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Title>) => (
  <DialogPrimitive.Title className={cn('text-base font-semibold', className)} {...props} />
)

export const DialogDescription = ({
  className,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Description>) => (
  <DialogPrimitive.Description
    className={cn('mt-1.5 text-sm text-text-secondary', className)}
    {...props}
  />
)

export const DialogClose = DialogPrimitive.Close
