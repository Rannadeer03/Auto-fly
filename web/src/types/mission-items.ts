// Mirrors server/models/manual_mission.py's discriminated union — the
// request-side shape for Manual Mission Mode's ordered mission-item list.
// Adding a new MAVLink item type later means adding one variant here and
// one branch wherever `item.type` is switched on (manual-mission-layer.tsx,
// the future inspector) — not restructuring the list itself.
import type { ManualItemInput } from '@/types/mission'

export type MissionItemType = 'takeoff' | 'waypoint' | 'loiter' | 'rtl' | 'land' | 'change_speed'

interface MissionItemBase {
  /** Stable client-generated identity — survives reordering/insertion, so
   * selection/inspector state (ui-store's selectedManualItemId) never goes
   * stale the way an array-index key would once items can be reordered. */
  id: string
}

export interface TakeoffItem extends MissionItemBase {
  type: 'takeoff'
  lat: number
  lng: number
  altitude: number
}

export interface WaypointItem extends MissionItemBase {
  type: 'waypoint'
  lat: number
  lng: number
  altitude: number
}

export interface LoiterItem extends MissionItemBase {
  type: 'loiter'
  lat: number
  lng: number
  altitude: number
  holdTimeS: number
}

export interface RtlItem extends MissionItemBase {
  type: 'rtl'
}

export interface LandItem extends MissionItemBase {
  type: 'land'
  lat: number
  lng: number
}

export interface ChangeSpeedItem extends MissionItemBase {
  type: 'change_speed'
  speedMs: number
}

export type MissionItem =
  | TakeoffItem
  | WaypointItem
  | LoiterItem
  | RtlItem
  | LandItem
  | ChangeSpeedItem

/** Items with a real lat/lng position on the map — used to filter which
 * items get a marker/appear in the connecting line. */
export type PositionedMissionItem = TakeoffItem | WaypointItem | LoiterItem | LandItem

export function hasPosition(item: MissionItem): item is PositionedMissionItem {
  return item.type === 'takeoff' || item.type === 'waypoint' || item.type === 'loiter' || item.type === 'land'
}

export function createItemId(): string {
  return crypto.randomUUID()
}

/** Converts one internal MissionItem (camelCase, map-friendly) to the
 * wire-format ManualItemInput the backend expects (types/mission.ts) —
 * reused by every request-building hook so the mapping lives in one place. */
export function toManualItemInput(item: MissionItem): ManualItemInput {
  switch (item.type) {
    case 'takeoff':
      return { type: 'takeoff', lat: item.lat, lon: item.lng, altitude_m: item.altitude }
    case 'waypoint':
      return { type: 'waypoint', lat: item.lat, lon: item.lng, altitude_m: item.altitude }
    case 'loiter':
      return {
        type: 'loiter', lat: item.lat, lon: item.lng,
        altitude_m: item.altitude, hold_time_s: item.holdTimeS,
      }
    case 'land':
      return { type: 'land', lat: item.lat, lon: item.lng }
    case 'change_speed':
      return { type: 'change_speed', speed_ms: item.speedMs }
    case 'rtl':
      return { type: 'rtl' }
  }
}

/** Reverse of toManualItemInput() — rehydrates a MissionItem (with a fresh
 * client-side id) from the wire format, e.g. when redeploying a saved
 * Mission Library entry back into the draft store. */
export function fromManualItemInput(item: ManualItemInput): MissionItem {
  const id = createItemId()
  switch (item.type) {
    case 'takeoff':
      return { id, type: 'takeoff', lat: item.lat, lng: item.lon, altitude: item.altitude_m }
    case 'waypoint':
      return { id, type: 'waypoint', lat: item.lat, lng: item.lon, altitude: item.altitude_m }
    case 'loiter':
      return {
        id, type: 'loiter', lat: item.lat, lng: item.lon,
        altitude: item.altitude_m, holdTimeS: item.hold_time_s,
      }
    case 'land':
      return { id, type: 'land', lat: item.lat, lng: item.lon }
    case 'change_speed':
      return { id, type: 'change_speed', speedMs: item.speed_ms }
    case 'rtl':
      return { id, type: 'rtl' }
  }
}
