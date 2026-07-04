import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import { useMapInstance } from '@/features/map/map-context'
import { useMissionDraftStore } from '@/store/mission-draft-store'
import { MAV_CMD } from '@/constants/mavlink'

function pinElement(color: string, label: string): HTMLDivElement {
  const el = document.createElement('div')
  el.style.display = 'flex'
  el.style.flexDirection = 'column'
  el.style.alignItems = 'center'
  el.style.transform = 'translateY(-50%)'
  el.innerHTML = `
    <div style="background:${color};color:#090b10;font-size:10px;font-weight:700;padding:2px 6px;border-radius:4px;white-space:nowrap;margin-bottom:2px;box-shadow:0 2px 8px rgba(0,0,0,0.4)">${label}</div>
    <svg width="20" height="20" viewBox="0 0 24 24" style="filter: drop-shadow(0 2px 4px rgba(0,0,0,0.5))">
      <path d="M12 2C7.6 2 4 5.6 4 10c0 6 8 12 8 12s8-6 8-12c0-4.4-3.6-8-8-8z" fill="${color}"/>
      <circle cx="12" cy="10" r="3" fill="#090b10"/>
    </svg>
  `
  return el
}

/** Home and takeoff pins, derived from the currently generated/loaded
 * mission (waypoint 0 = home, first NAV_TAKEOFF = takeoff point). */
export function MissionAnchors() {
  const map = useMapInstance()
  const mission = useMissionDraftStore((s) => s.generated?.mission_info ?? null)
  const homeMarkerRef = useRef<maplibregl.Marker | null>(null)
  const takeoffMarkerRef = useRef<maplibregl.Marker | null>(null)

  useEffect(() => {
    if (!map) return
    homeMarkerRef.current = new maplibregl.Marker({ element: pinElement('#60a5fa', 'HOME') })
    takeoffMarkerRef.current = new maplibregl.Marker({
      element: pinElement('#34d399', 'TAKEOFF'),
    })
    return () => {
      homeMarkerRef.current?.remove()
      takeoffMarkerRef.current?.remove()
    }
  }, [map])

  useEffect(() => {
    if (!map || !homeMarkerRef.current || !takeoffMarkerRef.current) return

    if (!mission) {
      homeMarkerRef.current.remove()
      takeoffMarkerRef.current.remove()
      return
    }

    const home = mission.waypoints[0]
    const takeoff = mission.waypoints.find((w) => w.command === MAV_CMD.NAV_TAKEOFF)

    if (home) {
      homeMarkerRef.current.setLngLat([home.longitude, home.latitude]).addTo(map)
    }
    if (takeoff) {
      takeoffMarkerRef.current.setLngLat([takeoff.longitude, takeoff.latitude]).addTo(map)
    }
  }, [map, mission])

  return null
}
