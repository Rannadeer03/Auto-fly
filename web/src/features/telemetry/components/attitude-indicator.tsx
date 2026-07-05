interface AttitudeIndicatorProps {
  rollDeg: number
  pitchDeg: number
}

/** Minimal artificial horizon — CSS-transform only, GPU-accelerated, no
 * canvas/redraw cost per telemetry tick. */
export function AttitudeIndicator({ rollDeg, pitchDeg }: AttitudeIndicatorProps) {
  const pitchOffsetPx = Math.max(-40, Math.min(40, pitchDeg * 1.2))

  return (
    <div className="relative h-40 w-40 overflow-hidden rounded-full border-2 border-border bg-surface-3">
      <div
        className="absolute inset-[-50%]"
        style={{
          transform: `rotate(${-rollDeg}deg) translateY(${pitchOffsetPx}px)`,
          transition: 'transform 120ms linear',
        }}
      >
        <div className="absolute inset-0 top-1/2 bg-info-500/40" />
        <div className="absolute inset-0 bottom-1/2 bg-warning-500/25" />
        <div className="absolute left-0 right-0 top-1/2 h-px bg-text-primary/70" />
      </div>
      <div className="absolute left-1/2 top-1/2 h-0.5 w-10 -translate-x-1/2 -translate-y-1/2 bg-accent-400" />
      <div className="absolute left-1/2 top-1/2 h-10 w-0.5 -translate-x-1/2 -translate-y-1/2 bg-accent-400/60" />
    </div>
  )
}
