import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import { useMapInstance } from '@/features/map/map-context'
import { useTelemetry } from '@/hooks/use-telemetry'

function createDroneElement(): HTMLDivElement {
  const el = document.createElement('div')
  el.style.width = '34px'
  el.style.height = '34px'
  el.style.willChange = 'transform'
  el.innerHTML = `
    <svg viewBox="0 0 24 24" width="34" height="34" style="filter: drop-shadow(0 0 6px rgba(34,211,238,0.65))">
      <circle cx="12" cy="12" r="10" fill="rgba(34,211,238,0.15)" stroke="#22d3ee" stroke-width="1.5" />
      <path d="M12 4 L17 15 L12 12 L7 15 Z" fill="#22d3ee" />
    </svg>
  `
  return el
}

/** Live drone position + heading, GPU-transformed (rotation via CSS, no
 * React re-render per telemetry tick beyond the marker's own transform). */
export function DroneMarker() {
  const map = useMapInstance()
  const { data: telemetry } = useTelemetry()
  const markerRef = useRef<maplibregl.Marker | null>(null)

  useEffect(() => {
    if (!map) return
    const el = createDroneElement()
    const marker = new maplibregl.Marker({ element: el, rotationAlignment: 'map' })
    markerRef.current = marker
    return () => {
      marker.remove()
      markerRef.current = null
    }
  }, [map])

  useEffect(() => {
    const marker = markerRef.current
    if (!marker || !telemetry?.connected) return
    const { latitude, longitude, heading } = telemetry.position
    if (latitude === 0 && longitude === 0) return

    marker.setLngLat([longitude, latitude])
    marker.setRotation(heading)
    if (!marker.getElement().isConnected) marker.addTo(map!)
  }, [telemetry, map])

  useEffect(() => {
    if (!telemetry?.connected && markerRef.current) {
      markerRef.current.remove()
    }
  }, [telemetry?.connected])

  return null
}
