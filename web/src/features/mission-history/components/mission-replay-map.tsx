import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { LineString } from 'geojson'
import { MAP_STYLE } from '@/constants/map'
import type { ImageMetadata } from '@/types/mission-history'

interface MissionReplayMapProps {
  images: ImageMetadata[]
  selectedFilename?: string | null
  onSelectImage?: (filename: string) => void
}

const POINTS_SOURCE = 'replay-points'
const POINTS_LAYER = 'replay-points-circle'

/** Self-contained map for a single finished mission: flight path traced
 * from geotagged capture positions, one marker per image. Clicking a point
 * (or selecting an image in the gallery) highlights the exact capture
 * location — independent MapLibre instance from the mission-planning map,
 * which stays alive in the background. */
export function MissionReplayMap({ images, selectedFilename, onSelectImage }: MissionReplayMapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const selectedRef = useRef<string | null | undefined>(selectedFilename)

  useEffect(() => {
    if (!containerRef.current) return
    const valid = images.filter((p) => p.latitude !== 0 || p.longitude !== 0)
    const coords = valid.map((p) => [p.longitude, p.latitude] as [number, number])

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: MAP_STYLE,
      center: coords[0] ?? [77.5946, 12.9716],
      zoom: coords.length ? 16 : 3,
      attributionControl: { compact: true },
      fadeDuration: 0,
    })
    mapRef.current = map

    map.on('load', () => {
      if (coords.length >= 2) {
        const line: LineString = { type: 'LineString', coordinates: coords }
        map.addSource('replay-path', {
          type: 'geojson',
          data: { type: 'Feature', properties: {}, geometry: line },
        })
        map.addLayer({
          id: 'replay-path-line',
          type: 'line',
          source: 'replay-path',
          paint: { 'line-color': '#22d3ee', 'line-width': 2, 'line-opacity': 0.85 },
        })
      }

      if (coords.length >= 1) {
        map.addSource(POINTS_SOURCE, {
          type: 'geojson',
          promoteId: 'filename',
          data: {
            type: 'FeatureCollection',
            features: valid.map((p) => ({
              type: 'Feature',
              properties: { filename: p.filename },
              geometry: { type: 'Point', coordinates: [p.longitude, p.latitude] },
            })),
          },
        })
        map.addLayer({
          id: POINTS_LAYER,
          type: 'circle',
          source: POINTS_SOURCE,
          paint: {
            'circle-radius': ['case', ['boolean', ['feature-state', 'selected'], false], 8, 3.5],
            'circle-color': [
              'case',
              ['boolean', ['feature-state', 'selected'], false],
              '#22d3ee',
              '#34d399',
            ],
            'circle-stroke-width': ['case', ['boolean', ['feature-state', 'selected'], false], 2, 1],
            'circle-stroke-color': '#090b10',
          },
        })

        map.on('mouseenter', POINTS_LAYER, () => {
          map.getCanvas().style.cursor = 'pointer'
        })
        map.on('mouseleave', POINTS_LAYER, () => {
          map.getCanvas().style.cursor = ''
        })
        map.on('click', POINTS_LAYER, (e) => {
          const filename = e.features?.[0]?.properties?.filename
          if (filename) onSelectImage?.(filename)
        })

        if (selectedRef.current) {
          map.setFeatureState({ source: POINTS_SOURCE, id: selectedRef.current }, { selected: true })
        }

        const bounds = coords.reduce(
          (b, c) => b.extend(c),
          new maplibregl.LngLatBounds(coords[0], coords[0]),
        )
        map.fitBounds(bounds, { padding: 40, duration: 0 })
      }
    })

    return () => {
      map.remove()
      mapRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [images])

  // Highlight the selected image without re-building the whole source.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const previous = selectedRef.current
    const apply = () => {
      if (!map.getSource(POINTS_SOURCE)) return
      if (previous) map.setFeatureState({ source: POINTS_SOURCE, id: previous }, { selected: false })
      if (selectedFilename) {
        map.setFeatureState({ source: POINTS_SOURCE, id: selectedFilename }, { selected: true })
        const image = images.find((p) => p.filename === selectedFilename)
        if (image && (image.latitude !== 0 || image.longitude !== 0)) {
          map.flyTo({ center: [image.longitude, image.latitude], zoom: Math.max(map.getZoom(), 18), duration: 400 })
        }
      }
      selectedRef.current = selectedFilename
    }
    if (map.isStyleLoaded()) apply()
    else map.once('load', apply)
  }, [selectedFilename, images])

  return <div ref={containerRef} className="h-full w-full rounded-[var(--radius-panel)]" />
}
