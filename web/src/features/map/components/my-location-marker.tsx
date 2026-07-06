import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import { useMapInstance } from '@/features/map/map-context'
import { useMyLocation } from '@/hooks/use-my-location'
import { useGeolocationStore } from '@/store/geolocation-store'

function createMyLocationElement(): HTMLDivElement {
  const el = document.createElement('div')
  el.style.display = 'flex'
  el.style.flexDirection = 'column'
  el.style.alignItems = 'center'
  el.innerHTML = `
    <div style="background:#818cf8;color:#090b10;font-size:10px;font-weight:700;padding:2px 6px;border-radius:4px;white-space:nowrap;margin-bottom:2px;box-shadow:0 2px 8px rgba(0,0,0,0.4)">My Location</div>
    <svg viewBox="0 0 22 22" width="22" height="22" style="filter: drop-shadow(0 0 4px rgba(99,102,241,0.7))">
      <circle cx="11" cy="11" r="9" fill="rgba(99,102,241,0.18)" stroke="#818cf8" stroke-width="1.5" />
      <circle cx="11" cy="11" r="4" fill="#818cf8" stroke="#e0e7ff" stroke-width="1.5" />
    </svg>
  `
  return el
}

/** Browser/laptop GPS position — entirely independent of drone telemetry.
 * Owns the single `useMyLocation()` watcher; auto-centers the map once on
 * the first fix only, so manual panning afterwards is never overridden. */
export function MyLocationMarker() {
  useMyLocation()
  const map = useMapInstance()
  const position = useGeolocationStore((s) => s.position)
  const markerRef = useRef<maplibregl.Marker | null>(null)
  const hasCenteredRef = useRef(false)

  useEffect(() => {
    if (!map) return
    const marker = new maplibregl.Marker({ element: createMyLocationElement() })
    markerRef.current = marker
    return () => {
      marker.remove()
      markerRef.current = null
    }
  }, [map])

  useEffect(() => {
    if (!map || !markerRef.current || !position) return
    markerRef.current.setLngLat([position.lng, position.lat])
    if (!markerRef.current.getElement().isConnected) markerRef.current.addTo(map)

    if (!hasCenteredRef.current) {
      hasCenteredRef.current = true
      map.flyTo({ center: [position.lng, position.lat], zoom: Math.max(map.getZoom(), 16) })
    }
  }, [map, position])

  return null
}
