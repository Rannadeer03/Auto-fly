export function formatDistance(meters: number): string {
  if (meters >= 1000) return `${(meters / 1000).toFixed(2)} km`
  return `${meters.toFixed(0)} m`
}

export function formatArea(m2: number): string {
  if (m2 >= 10_000) return `${(m2 / 10_000).toFixed(2)} ha`
  return `${m2.toFixed(0)} m²`
}

export function formatDuration(minutes: number): string {
  if (minutes < 1) return `${Math.round(minutes * 60)} s`
  const wholeMin = Math.floor(minutes)
  const seconds = Math.round((minutes - wholeMin) * 60)
  if (wholeMin < 60) return seconds > 0 ? `${wholeMin}m ${seconds}s` : `${wholeMin}m`
  const hours = Math.floor(wholeMin / 60)
  const remMin = wholeMin % 60
  return `${hours}h ${remMin}m`
}

export function formatPercent(value: number, digits = 0): string {
  return `${value.toFixed(digits)}%`
}

export function formatCoord(value: number): string {
  return value.toFixed(6)
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let value = bytes
  let unitIndex = -1
  do {
    value /= 1024
    unitIndex++
  } while (value >= 1024 && unitIndex < units.length - 1)
  return `${value.toFixed(1)} ${units[unitIndex]}`
}

export function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}
