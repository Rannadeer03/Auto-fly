import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import type { Feature, FeatureCollection, LineString, Point } from 'geojson'
import { useMapInstance } from '@/features/map/map-context'
import { useMissionDraftStore } from '@/store/mission-draft-store'
import { useUiStore } from '@/store/ui-store'
import { MAV_CMD } from '@/constants/mavlink'
import type { WaypointItem } from '@/types/mission'

const PATH_SOURCE = 'survey-path'
const PATH_LINE_LAYER = 'survey-path-line'
const PATH_ARROW_LAYER = 'survey-path-arrows'
const WAYPOINTS_SOURCE = 'survey-waypoints'
const WAYPOINTS_CIRCLE_LAYER = 'survey-waypoints-circle'
const WAYPOINTS_LABEL_LAYER = 'survey-waypoints-label'

function isPathPoint(wp: WaypointItem): boolean {
  return (
    wp.command !== MAV_CMD.DO_CHANGE_SPEED &&
    wp.command !== MAV_CMD.NAV_RTL &&
    !(wp.current && wp.latitude === 0 && wp.longitude === 0)
  )
}

function buildPathGeoJSON(waypoints: WaypointItem[]): FeatureCollection<LineString> {
  const coords = waypoints.filter(isPathPoint).map((w) => [w.longitude, w.latitude])
  const feature: Feature<LineString> = {
    type: 'Feature',
    properties: {},
    geometry: { type: 'LineString', coordinates: coords },
  }
  return { type: 'FeatureCollection', features: coords.length >= 2 ? [feature] : [] }
}

function buildWaypointsGeoJSON(waypoints: WaypointItem[]): FeatureCollection<Point> {
  let captureNumber = 0
  const features: Feature<Point>[] = waypoints
    .filter((w) => w.command === MAV_CMD.NAV_WAYPOINT && !w.current)
    .map((w) => {
      if (w.is_capture_point) captureNumber += 1
      return {
        type: 'Feature',
        properties: {
          index: w.index,
          isCapturePoint: w.is_capture_point,
          captureNumber: w.is_capture_point ? captureNumber : null,
          altitude: w.altitude,
          holdTimeS: w.param1,
        },
        geometry: { type: 'Point', coordinates: [w.longitude, w.latitude] },
      } satisfies Feature<Point>
    })
  return { type: 'FeatureCollection', features }
}

/**
 * Renders the generated survey as GPU-accelerated vector layers rather than
 * per-point DOM markers — the only way this stays smooth at 1000+ waypoints.
 * A single GeoJSON source + circle/symbol layers handles numbering, camera
 * points, and selection highlighting entirely on the GPU.
 */
export function SurveyLayer() {
  const map = useMapInstance()
  const mission = useMissionDraftStore((s) => s.generated?.mission_info ?? null)
  const selectedIndex = useUiStore((s) => s.selectedWaypointIndex)
  const selectWaypoint = useUiStore((s) => s.selectWaypoint)
  const popupRef = useRef<maplibregl.Popup | null>(null)
  const selectedIndexRef = useRef<number | null>(null)

  useEffect(() => {
    if (!map) return

    map.addSource(PATH_SOURCE, {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
    })
    map.addLayer({
      id: PATH_LINE_LAYER,
      type: 'line',
      source: PATH_SOURCE,
      paint: {
        'line-color': '#22d3ee',
        'line-width': 2,
        'line-opacity': 0.85,
      },
      layout: { 'line-join': 'round', 'line-cap': 'round' },
    })
    map.addLayer({
      id: PATH_ARROW_LAYER,
      type: 'symbol',
      source: PATH_SOURCE,
      layout: {
        'symbol-placement': 'line',
        'symbol-spacing': 60,
        'text-field': '➤',
        'text-size': 13,
        'text-rotation-alignment': 'map',
        'text-keep-upright': false,
        'text-allow-overlap': true,
        'text-ignore-placement': true,
      },
      paint: {
        'text-color': '#22d3ee',
        'text-opacity': 0.9,
      },
    })

    map.addSource(WAYPOINTS_SOURCE, {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
      promoteId: 'index',
    })
    map.addLayer({
      id: WAYPOINTS_CIRCLE_LAYER,
      type: 'circle',
      source: WAYPOINTS_SOURCE,
      paint: {
        'circle-radius': ['case', ['boolean', ['feature-state', 'selected'], false], 9, 6],
        'circle-color': [
          'case',
          ['get', 'isCapturePoint'],
          '#34d399',
          '#60a5fa',
        ],
        'circle-stroke-width': ['case', ['boolean', ['feature-state', 'selected'], false], 3, 1.5],
        'circle-stroke-color': '#090b10',
      },
    })
    map.addLayer({
      id: WAYPOINTS_LABEL_LAYER,
      type: 'symbol',
      source: WAYPOINTS_SOURCE,
      layout: {
        'text-field': ['to-string', ['coalesce', ['get', 'captureNumber'], '']],
        'text-size': 10,
        'text-allow-overlap': true,
        'text-ignore-placement': true,
      },
      paint: {
        'text-color': '#090b10',
        'text-halo-width': 0,
      },
    })

    const canvas = map.getCanvas()

    const onEnter = () => {
      canvas.style.cursor = 'pointer'
    }
    const onLeave = () => {
      canvas.style.cursor = ''
      popupRef.current?.remove()
    }
    const onMove = (e: maplibregl.MapLayerMouseEvent) => {
      const feature = e.features?.[0]
      if (!feature) return
      const props = feature.properties as {
        index: number
        isCapturePoint: boolean
        captureNumber: number | null
        altitude: number
        holdTimeS: number
      }
      const [lng, lat] = (feature.geometry as Point).coordinates as [number, number]

      if (!popupRef.current) {
        popupRef.current = new maplibregl.Popup({
          closeButton: false,
          closeOnClick: false,
          offset: 12,
        })
      }
      popupRef.current
        .setLngLat([lng, lat])
        .setHTML(
          `<div style="font-size:11px;line-height:1.5">
            <div style="font-weight:700;margin-bottom:2px">Waypoint ${props.index}</div>
            ${props.isCapturePoint ? `<div>📷 Capture #${props.captureNumber}</div>` : ''}
            <div>Alt: ${props.altitude.toFixed(0)} m</div>
            ${props.holdTimeS > 0 ? `<div>Hold: ${props.holdTimeS.toFixed(1)}s</div>` : ''}
          </div>`,
        )
        .addTo(map)
    }
    const onClick = (e: maplibregl.MapLayerMouseEvent) => {
      const feature = e.features?.[0]
      if (!feature) return
      selectWaypoint(feature.properties?.index ?? null)
    }

    map.on('mouseenter', WAYPOINTS_CIRCLE_LAYER, onEnter)
    map.on('mouseleave', WAYPOINTS_CIRCLE_LAYER, onLeave)
    map.on('mousemove', WAYPOINTS_CIRCLE_LAYER, onMove)
    map.on('click', WAYPOINTS_CIRCLE_LAYER, onClick)

    return () => {
      map.off('mouseenter', WAYPOINTS_CIRCLE_LAYER, onEnter)
      map.off('mouseleave', WAYPOINTS_CIRCLE_LAYER, onLeave)
      map.off('mousemove', WAYPOINTS_CIRCLE_LAYER, onMove)
      map.off('click', WAYPOINTS_CIRCLE_LAYER, onClick)
      popupRef.current?.remove()
      for (const id of [WAYPOINTS_LABEL_LAYER, WAYPOINTS_CIRCLE_LAYER, PATH_ARROW_LAYER, PATH_LINE_LAYER]) {
        if (map.getLayer(id)) map.removeLayer(id)
      }
      for (const id of [WAYPOINTS_SOURCE, PATH_SOURCE]) {
        if (map.getSource(id)) map.removeSource(id)
      }
    }
  }, [map, selectWaypoint])

  useEffect(() => {
    if (!map) return
    const pathSource = map.getSource(PATH_SOURCE) as maplibregl.GeoJSONSource | undefined
    const waypointsSource = map.getSource(WAYPOINTS_SOURCE) as maplibregl.GeoJSONSource | undefined
    if (!pathSource || !waypointsSource) return

    const waypoints = mission?.waypoints ?? []
    pathSource.setData(buildPathGeoJSON(waypoints))
    waypointsSource.setData(buildWaypointsGeoJSON(waypoints))
  }, [map, mission])

  // Feature-state selection highlight — avoids re-diffing the whole source
  // just to highlight one point.
  useEffect(() => {
    if (!map) return
    const previous = selectedIndexRef.current
    if (previous !== null) {
      map.setFeatureState({ source: WAYPOINTS_SOURCE, id: previous }, { selected: false })
    }
    if (selectedIndex !== null) {
      map.setFeatureState({ source: WAYPOINTS_SOURCE, id: selectedIndex }, { selected: true })
    }
    selectedIndexRef.current = selectedIndex
  }, [map, selectedIndex])

  return null
}
