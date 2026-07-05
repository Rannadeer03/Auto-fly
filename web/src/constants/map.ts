import type { StyleSpecification } from 'maplibre-gl'

export type BaseLayerId = 'satellite' | 'street' | 'hybrid'

// ── Imagery provider (configurable) ─────────────────────────────────────────
//
// Default is Esri World Imagery — free, no API key, but its native tile
// resolution tops out around z19 in most regions (lower in some rural
// areas), which is what makes deep zoom on individual plants blurry: MapLibre
// is upscaling the highest tile it actually has, not failing to render.
// There is no free/key-less provider that goes meaningfully higher — true
// sub-city-block sharpness at z20+ requires a licensed provider (MapTiler
// Satellite, Mapbox Satellite, Maxar, Nearmap, etc).
//
// To use one: set these in web/.env (see web/.env.example) and rebuild.
// Nothing else in the app needs to change — every consumer goes through
// BASE_LAYER_VISIBLE_LAYERS / MAP_STYLE below.
const SATELLITE_TILE_URL =
  import.meta.env.VITE_SATELLITE_TILE_URL ??
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
const SATELLITE_MAX_ZOOM = Number(import.meta.env.VITE_SATELLITE_MAX_ZOOM ?? 19)
const SATELLITE_ATTRIBUTION = import.meta.env.VITE_SATELLITE_ATTRIBUTION ?? '© Esri'

const ESRI_LABELS_TILES = [
  'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
]
// The boundaries/places reference layer has much sparser coverage at depth
// than the imagery itself — capping it lower avoids a wall of 404s (and the
// "map stops rendering" symptom) once you're zoomed in past what it has.
const LABELS_MAX_ZOOM = 16

const OSM_TILES = ['https://tile.openstreetmap.org/{z}/{x}/{y}.png']
const OSM_MAX_ZOOM = 19

// The view is allowed to zoom in well past the imagery's native resolution:
// MapLibre overzooms cleanly (upscales the deepest tile it has) rather than
// stopping, which is what "precise waypoint placement" needs even when the
// last mile of sharpness depends on the provider's own coverage.
export const MAP_MAX_ZOOM = 22

// A single style containing every base layer as a raster layer with
// visibility toggled at runtime (setLayoutProperty) instead of swapping
// styles — avoids a full style/source reload (and losing our custom
// sources/layers) every time the user flips satellite/street/hybrid.
export const MAP_STYLE: StyleSpecification = {
  version: 8,
  glyphs: 'https://fonts.openmaptiles.org/{fontstack}/{range}.pbf',
  sources: {
    'esri-imagery': {
      type: 'raster',
      tiles: [SATELLITE_TILE_URL],
      tileSize: 256,
      maxzoom: SATELLITE_MAX_ZOOM,
      attribution: SATELLITE_ATTRIBUTION,
    },
    osm: {
      type: 'raster',
      tiles: OSM_TILES,
      tileSize: 256,
      maxzoom: OSM_MAX_ZOOM,
      attribution: '© OpenStreetMap contributors',
    },
    'esri-labels': {
      type: 'raster',
      tiles: ESRI_LABELS_TILES,
      tileSize: 256,
      maxzoom: LABELS_MAX_ZOOM,
      attribution: '© Esri',
    },
  },
  layers: [
    { id: 'esri-imagery-layer', type: 'raster', source: 'esri-imagery', layout: { visibility: 'visible' }, paint: { 'raster-fade-duration': 0 } },
    { id: 'osm-layer', type: 'raster', source: 'osm', layout: { visibility: 'none' }, paint: { 'raster-fade-duration': 0 } },
    { id: 'esri-labels-layer', type: 'raster', source: 'esri-labels', layout: { visibility: 'none' }, paint: { 'raster-fade-duration': 0 } },
  ],
}

export const BASE_LAYER_VISIBLE_LAYERS: Record<BaseLayerId, string[]> = {
  satellite: ['esri-imagery-layer'],
  street: ['osm-layer'],
  hybrid: ['esri-imagery-layer', 'esri-labels-layer'],
}

export const ALL_BASE_LAYER_IDS = ['esri-imagery-layer', 'osm-layer', 'esri-labels-layer']

export const BASE_LAYER_LABELS: Record<BaseLayerId, string> = {
  satellite: 'Satellite',
  street: 'Street',
  hybrid: 'Hybrid',
}

export const DEFAULT_MAP_CENTER: [number, number] = [77.5946, 12.9716] // [lng, lat]
export const DEFAULT_MAP_ZOOM = 17
