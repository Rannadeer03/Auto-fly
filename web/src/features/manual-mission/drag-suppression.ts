/**
 * Tiny shared, imperative (non-store) flag so a marker's dragend in
 * manual-mission-layer.tsx can tell manual-mission-tool.tsx's click
 * listener "this click is the tail end of a drag, not a placement click" —
 * without routing through zustand/React state for something this
 * transient and same-tick. See manual-mission-tool.tsx for why a raw DOM
 * listener (not MapLibre's own synthetic 'click') is needed here at all.
 */
let suppressUntil = 0

export function suppressNextClick(ms = 300): void {
  suppressUntil = Date.now() + ms
}

export function isClickSuppressed(): boolean {
  return Date.now() < suppressUntil
}
