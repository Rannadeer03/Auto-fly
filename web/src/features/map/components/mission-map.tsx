import { useEffect, useRef, useState, type ReactNode } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { MAP_STYLE, DEFAULT_MAP_CENTER, DEFAULT_MAP_ZOOM, MAP_MAX_ZOOM } from '@/constants/map'
import { MapContext } from '@/features/map/map-context'

interface MissionMapProps {
  children?: ReactNode
  className?: string
}

/**
 * Owns the single MapLibre GL instance for the app. Mounted once and kept
 * alive for the lifetime of the session (see App.tsx) — recreating the GL
 * context on every sidebar-section switch is expensive and causes visible
 * flicker with 1000+ waypoints on screen.
 */
export function MissionMap({ children, className }: MissionMapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const [map, setMap] = useState<maplibregl.Map | null>(null)

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return

    const instance = new maplibregl.Map({
      container: containerRef.current,
      style: MAP_STYLE,
      center: DEFAULT_MAP_CENTER,
      zoom: DEFAULT_MAP_ZOOM,
      // Let the view zoom in well past the imagery's native tile resolution —
      // MapLibre overzooms (upscales the deepest available tile) instead of
      // stopping, which is what precise waypoint placement needs. See
      // constants/map.ts for why sharpness is still capped by the provider.
      maxZoom: MAP_MAX_ZOOM,
      // A top-down survey tool has no use for tilt/rotation, and disabling
      // them removes a class of tile-loading edge cases at extreme zoom.
      pitchWithRotate: false,
      dragRotate: false,
      touchPitch: false,
      attributionControl: { compact: true },
      // GPU-accelerated, no easing jank on pan/zoom for large waypoint sets.
      fadeDuration: 0,
      // More headroom than the viewport-based default so panning back over
      // already-visited tiles at deep zoom doesn't re-fetch from the network.
      maxTileCacheSize: 200,
    })

    // Both bottom corners are permanently occupied by our own docked panels
    // (flight params/estimation bottom-right, waypoint detail bottom-left) —
    // native controls go up top, below our toolbar row (offset via CSS in
    // styles/globals.css targeting .maplibregl-ctrl-top-*).
    instance.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    instance.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'top-left')

    instance.on('load', () => {
      mapRef.current = instance
      setMap(instance)
    })

    // Individual tile failures (a region with no imagery at this zoom, a
    // flaky network) must never take down the whole map — log and move on.
    instance.on('error', (e) => {
      console.warn('Map error (tile or style issue, non-fatal):', e.error?.message ?? e)
    })

    // MapLibre measures the container once at construction and otherwise
    // only re-measures on a window 'resize' event. Our layout can resize
    // this container without the window ever resizing (sidebar collapse,
    // the flex column settling after fonts/CSS finish applying) — without
    // this the canvas can get stuck at a stale, wrong size.
    const resizeObserver = new ResizeObserver(() => instance.resize())
    resizeObserver.observe(containerRef.current)

    return () => {
      resizeObserver.disconnect()
      instance.remove()
      mapRef.current = null
      setMap(null)
    }
  }, [])

  return (
    <div className={className ?? 'absolute inset-0'}>
      {/* MapLibre owns this div's DOM imperatively (canvas, its own controls) —
          React must never render children into the same node, or MapLibre's
          internal elements end up stacked on top of our UI and swallow every
          click. The overlay below is a sibling in its own stacking context
          (z-10) so it always wins regardless of DOM insertion order.

          Position is inline, not a Tailwind class: MapLibre adds its own
          "maplibregl-map" class to this exact element, and maplibre-gl.css
          declares `.maplibregl-map { position: relative }` — equal
          specificity to our `.absolute` utility, so whichever stylesheet
          happens to load last would silently win and collapse the canvas
          to a content-sized (not viewport-filling) box. An inline style
          can't lose that tie. */}
      <div ref={containerRef} style={{ position: 'absolute', inset: 0 }} />
      <MapContext.Provider value={map}>
        {map && <div className="pointer-events-none absolute inset-0 z-10">{children}</div>}
      </MapContext.Provider>
    </div>
  )
}
