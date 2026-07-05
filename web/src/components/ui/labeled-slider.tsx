import * as SliderPrimitive from '@radix-ui/react-slider'
import { cn } from '@/utils/cn'

interface LabeledSliderProps {
  label: string
  value: number
  onChange: (value: number) => void
  min: number
  max: number
  step?: number
  unit?: string
  className?: string
}

/** Flight-parameter control: label + live value readout + Radix slider. */
export function LabeledSlider({
  label,
  value,
  onChange,
  min,
  max,
  step = 1,
  unit = '',
  className,
}: LabeledSliderProps) {
  return (
    <div className={cn('space-y-2', className)}>
      <div className="flex items-center justify-between text-xs">
        <span className="text-text-secondary">{label}</span>
        <span className="font-mono font-medium text-text-primary">
          {value}
          {unit}
        </span>
      </div>
      <SliderPrimitive.Root
        className="relative flex h-4 w-full touch-none select-none items-center"
        value={[value]}
        min={min}
        max={max}
        step={step}
        onValueChange={([v]) => onChange(v)}
      >
        <SliderPrimitive.Track className="relative h-1.5 grow rounded-full bg-surface-3">
          <SliderPrimitive.Range className="absolute h-full rounded-full bg-accent-500" />
        </SliderPrimitive.Track>
        <SliderPrimitive.Thumb
          className="block h-4 w-4 rounded-full border-2 border-accent-500 bg-canvas shadow transition-transform hover:scale-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500/50"
          aria-label={label}
        />
      </SliderPrimitive.Root>
    </div>
  )
}
