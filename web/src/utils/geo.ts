import type { LngLat } from '@/store/mission-draft-store'

const M_PER_DEG_LAT = 111_320

/**
 * Polygon area in m^2 via the shoelace formula over a local equirectangular
 * projection centred on the polygon centroid — the same approximation
 * server/services/grid_planner.py uses, so the frontend's live "Farm Area"
 * readout stays consistent with what the backend will compute the survey
 * grid over.
 */
export function polygonAreaM2(coords: LngLat[]): number {
  if (coords.length < 3) return 0

  const lat0 = coords.reduce((sum, [, lat]) => sum + lat, 0) / coords.length
  const mPerDegLon = M_PER_DEG_LAT * Math.cos((lat0 * Math.PI) / 180)

  const pts = coords.map(([lng, lat]) => [lng * mPerDegLon, lat * M_PER_DEG_LAT])

  let area = 0
  for (let i = 0; i < pts.length; i++) {
    const [x1, y1] = pts[i]
    const [x2, y2] = pts[(i + 1) % pts.length]
    area += x1 * y2 - x2 * y1
  }
  return Math.abs(area) / 2
}

export function m2ToHectares(m2: number): number {
  return m2 / 10_000
}

export function m2ToAcres(m2: number): number {
  return m2 / 4046.8564224
}

/** [lng, lat][] (map convention) -> [lat, lon][] (backend GridRequest convention). */
export function toBackendPolygon(coords: LngLat[]): [number, number][] {
  return coords.map(([lng, lat]) => [lat, lng])
}

/**
 * Optimal survey heading, computed the way DroneDeploy/Pix4D-style planners
 * do it: align flight lines parallel to the polygon's longest edge, which
 * minimizes the number of lawnmower passes (and therefore turns) for most
 * field shapes. Server-side grid_planner.py takes angle_deg as a plain
 * parameter with no opinion on what it should be — this is what fills that
 * gap "automatically, without user intervention" per the product spec,
 * entirely on the client so no backend change was needed.
 *
 * Returns degrees in [0, 180) — a survey line at angle A is identical to one
 * at A+180 (the sweep is symmetric), so the backend's 0-359 angle_deg range
 * is a superset of what this needs to express.
 */
export function longestEdgeAngleDeg(coords: LngLat[]): number {
  if (coords.length < 2) return 0

  const lat0 = coords.reduce((sum, [, lat]) => sum + lat, 0) / coords.length
  const mPerDegLon = M_PER_DEG_LAT * Math.cos((lat0 * Math.PI) / 180)
  const pts = coords.map(([lng, lat]) => [lng * mPerDegLon, lat * M_PER_DEG_LAT])

  let bestLenSq = -1
  let bestAngle = 0
  for (let i = 0; i < pts.length; i++) {
    const [x1, y1] = pts[i]
    const [x2, y2] = pts[(i + 1) % pts.length]
    const dx = x2 - x1
    const dy = y2 - y1
    const lenSq = dx * dx + dy * dy
    if (lenSq > bestLenSq) {
      bestLenSq = lenSq
      // Angle measured from the local +x (east) axis, matching
      // grid_planner.py's rotation convention.
      let angle = (Math.atan2(dy, dx) * 180) / Math.PI
      angle = ((angle % 180) + 180) % 180
      bestAngle = angle
    }
  }
  return bestAngle
}
