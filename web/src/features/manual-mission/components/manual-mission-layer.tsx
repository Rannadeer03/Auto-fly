import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import type { Feature, FeatureCollection, LineString } from 'geojson'
import { useMapInstance } from '@/features/map/map-context'
import { useMissionDraftStore } from '@/store/mission-draft-store'
import { useUiStore } from '@/store/ui-store'
import { suppressNextClick } from '@/features/manual-mission/drag-suppression'
import { hasPosition, type MissionItem } from '@/types/mission-items'

const LINE_SOURCE = 'manual-mission-path'
const LINE_LAYER = 'manual-mission-path-line'

const EMPTY_LINE: FeatureCollection<LineString> = { type: 'FeatureCollection', features: [] }

function pinElement(color: string, label: string): HTMLDivElement {
  const el = document.createElement('div')
  el.style.display = 'flex'
  el.style.flexDirection = 'column'
  el.style.alignItems = 'center'
  el.style.cursor = 'grab'
  el.innerHTML = `
    <div style="background:${color};color:#090b10;font-size:10px;font-weight:700;padding:2px 6px;border-radius:4px;white-space:nowrap;margin-bottom:2px;box-shadow:0 2px 8px rgba(0,0,0,0.4)">${label}</div>
    <svg width="20" height="20" viewBox="0 0 24 24" style="filter: drop-shadow(0 2px 4px rgba(0,0,0,0.5))">
      <path d="M12 2C7.6 2 4 5.6 4 10c0 6 8 12 8 12s8-6 8-12c0-4.4-3.6-8-8-8z" fill="${color}"/>
      <circle cx="12" cy="10" r="3" fill="#090b10"/>
    </svg>
  `
  return el
}

function waypointElement(number: number): HTMLDivElement {
  const el = document.createElement('div')
  el.style.width = '22px'
  el.style.height = '22px'
  el.style.borderRadius = '50%'
  el.style.display = 'flex'
  el.style.alignItems = 'center'
  el.style.justifyContent = 'center'
  el.style.background = '#22d3ee'
  el.style.color = '#090b10'
  el.style.fontSize = '11px'
  el.style.fontWeight = '700'
  el.style.border = '1.5px solid #090b10'
  el.style.boxShadow = '0 2px 6px rgba(0,0,0,0.5)'
  el.style.cursor = 'grab'
  el.textContent = String(number)
  return el
}

// Loiter/Land aren't placeable from today's UI yet (Phase 2B) — this
// generic marker keeps the rendering loop below already structured to
// handle them once they are, without another rewrite.
function genericItemElement(label: string, color: string): HTMLDivElement {
  const el = document.createElement('div')
  el.style.width = '20px'
  el.style.height = '20px'
  el.style.borderRadius = '4px'
  el.style.display = 'flex'
  el.style.alignItems = 'center'
  el.style.justifyContent = 'center'
  el.style.background = color
  el.style.color = '#090b10'
  el.style.fontSize = '10px'
  el.style.fontWeight = '700'
  el.style.border = '1.5px solid #090b10'
  el.style.boxShadow = '0 2px 6px rgba(0,0,0,0.5)'
  el.style.cursor = 'grab'
  el.textContent = label
  return el
}

/**
 * Renders Manual Mission Mode's interactive state: a draggable Launch
 * marker (the takeoff-type item in `manualItems`), a draggable Home
 * marker (its own field — never a flown item), one draggable marker per
 * remaining positional item, and a connecting line from Launch through
 * them in order (not through Home — RTL returns to the vehicle's actual
 * arm position automatically, there is no drawn "last leg back to Home").
 *
 * Deliberately not built on SurveyLayer's GPU circle layer: manual mode
 * needs native drag-and-drop per point, which MapLibre only supports on
 * DOM `Marker`s, not paint-layer features. A manual mission has at most a
 * few dozen points, so plain markers are both simpler and fast enough.
 */
export function ManualMissionLayer() {
  const map = useMapInstance()
  const manualHome = useMissionDraftStore((s) => s.manualHome)
  const manualItems = useMissionDraftStore((s) => s.manualItems)
  const setManualHome = useMissionDraftStore((s) => s.setManualHome)
  const moveManualItem = useMissionDraftStore((s) => s.moveManualItem)
  const selectManualItem = useUiStore((s) => s.selectManualItem)

  const homeMarkerRef = useRef<maplibregl.Marker | null>(null)
  const itemMarkersRef = useRef<maplibregl.Marker[]>([])

  // Line source/layer — created once, updated in place.
  useEffect(() => {
    if (!map) return
    map.addSource(LINE_SOURCE, { type: 'geojson', data: EMPTY_LINE })
    map.addLayer({
      id: LINE_LAYER,
      type: 'line',
      source: LINE_SOURCE,
      paint: { 'line-color': '#22d3ee', 'line-width': 2, 'line-opacity': 0.85, 'line-dasharray': [2, 1] },
      layout: { 'line-join': 'round', 'line-cap': 'round' },
    })
    return () => {
      if (map.getLayer(LINE_LAYER)) map.removeLayer(LINE_LAYER)
      if (map.getSource(LINE_SOURCE)) map.removeSource(LINE_SOURCE)
    }
  }, [map])

  useEffect(() => {
    if (!map) return
    const source = map.getSource(LINE_SOURCE) as maplibregl.GeoJSONSource | undefined
    if (!source) return
    const coords: [number, number][] = manualItems.filter(hasPosition).map((it) => [it.lng, it.lat])
    const feature: Feature<LineString> = {
      type: 'Feature',
      properties: {},
      geometry: { type: 'LineString', coordinates: coords },
    }
    source.setData(coords.length >= 2 ? { type: 'FeatureCollection', features: [feature] } : EMPTY_LINE)
  }, [map, manualItems])

  // Home marker — a separate field, not a mission item (never flown
  // through; see mission-draft-store.ts's comment on manualHome).
  useEffect(() => {
    if (!map) return
    if (!manualHome) {
      homeMarkerRef.current?.remove()
      homeMarkerRef.current = null
      return
    }
    if (!homeMarkerRef.current) {
      const marker = new maplibregl.Marker({ element: pinElement('#60a5fa', 'HOME'), draggable: true })
      marker.on('dragend', () => {
        suppressNextClick()
        const ll = marker.getLngLat()
        setManualHome([ll.lng, ll.lat])
      })
      homeMarkerRef.current = marker
    }
    homeMarkerRef.current.setLngLat(manualHome).addTo(map)
  }, [map, manualHome, setManualHome])

  // Item markers — full rebuild on every change. A manual mission tops out
  // at a few dozen points, so recreating them on add/remove/drag is
  // imperceptible, and (now that identity is a stable `id`, not an array
  // index) this stays correct no matter how Phase 2B/2E reorders the list.
  useEffect(() => {
    if (!map) return
    itemMarkersRef.current.forEach((m) => m.remove())

    let waypointNumber = 0
    const markers: maplibregl.Marker[] = []

    for (const item of manualItems) {
      if (item.type === 'takeoff') {
        const marker = new maplibregl.Marker({ element: pinElement('#34d399', 'LAUNCH'), draggable: true })
        marker.setLngLat([item.lng, item.lat]).addTo(map)
        marker.on('dragend', () => {
          suppressNextClick()
          const ll = marker.getLngLat()
          moveManualItem(item.id, [ll.lng, ll.lat])
        })
        markers.push(marker)
        continue
      }
      if (!hasPosition(item)) continue // RTL / Change Speed carry no map position (yet)

      const el = elementForItem(item, item.type === 'waypoint' ? ++waypointNumber : 0)
      const marker = new maplibregl.Marker({ element: el, draggable: true })
      marker.setLngLat([item.lng, item.lat]).addTo(map)

      let dragged = false
      marker.on('dragstart', () => {
        dragged = true
      })
      marker.on('dragend', () => {
        suppressNextClick()
        const ll = marker.getLngLat()
        moveManualItem(item.id, [ll.lng, ll.lat])
      })
      el.addEventListener('click', (e) => {
        e.stopPropagation()
        if (dragged) {
          dragged = false
          return
        }
        selectManualItem(item.id)
      })
      markers.push(marker)
    }

    itemMarkersRef.current = markers
    return () => {
      markers.forEach((m) => m.remove())
    }
  }, [map, manualItems, moveManualItem, selectManualItem])

  // Full teardown when this component unmounts (switching back to Survey
  // mode) — the effects above only clean up their own marker on a value
  // change, not on unmount, since a null/empty value legitimately means
  // "nothing placed yet" as well as "component going away."
  useEffect(() => {
    return () => {
      homeMarkerRef.current?.remove()
      itemMarkersRef.current.forEach((m) => m.remove())
    }
  }, [])

  return null
}

function elementForItem(item: MissionItem, waypointNumber: number): HTMLDivElement {
  switch (item.type) {
    case 'waypoint':
      return waypointElement(waypointNumber)
    case 'loiter':
      return genericItemElement('L', '#facc15')
    case 'land':
      return genericItemElement('LD', '#f87171')
    default:
      return waypointElement(waypointNumber)
  }
}
