import { create } from 'zustand'
import type { CaptureMode, GridResponse } from '@/types/mission'
import {
  createItemId,
  hasPosition,
  type ChangeSpeedItem,
  type LandItem,
  type LoiterItem,
  type MissionItem,
  type MissionItemType,
  type RtlItem,
  type TakeoffItem,
  type WaypointItem,
} from '@/types/mission-items'

// [lng, lat] — GeoJSON / MapLibre / terra-draw convention. Converted to the
// backend's [lat, lon] convention only at the API boundary (see
// features/survey/utils/polygon.ts).
export type LngLat = [number, number]

export type ImageFormat = 'jpeg' | 'png'
export type SurveyDirection = 'auto' | 'manual'

export interface FlightParams {
  altitudeM: number
  speedMs: number
  frontOverlapPct: number
  sideOverlapPct: number
  angleDeg: number
  surveyDirection: SurveyDirection
  holdTimeS: number
  captureMode: CaptureMode
  cameraAngleDeg: number
  imageFormat: ImageFormat
  missionName: string
  missionDescription: string
  // Mission Settings (Manual Mission Mode). Only acceptanceRadiusM has a
  // direct MAVLink mission-item mapping (applied server-side as every
  // waypoint/loiter/land item's param2 — see manual_mission_builder.py).
  // The five *SpeedMs fields and cameraTriggerDistanceM are vehicle
  // parameters / a future camera-automation feature, not mission items —
  // they're stored and round-tripped through the Mission Library but not
  // yet applied to the generated mission.
  takeoffSpeedMs: number
  climbSpeedMs: number
  descentSpeedMs: number
  rtlSpeedMs: number
  landSpeedMs: number
  acceptanceRadiusM: number
  cameraTriggerDistanceM: number
}

export const DEFAULT_FLIGHT_PARAMS: FlightParams = {
  altitudeM: 30,
  speedMs: 5,
  frontOverlapPct: 75,
  sideOverlapPct: 65,
  angleDeg: 0,
  surveyDirection: 'auto',
  holdTimeS: 1,
  captureMode: 'hover',
  cameraAngleDeg: -90,
  imageFormat: 'jpeg',
  missionName: '',
  missionDescription: '',
  takeoffSpeedMs: 2,
  climbSpeedMs: 3,
  descentSpeedMs: 2,
  rtlSpeedMs: 5,
  landSpeedMs: 0.5,
  acceptanceRadiusM: 2,
  cameraTriggerDistanceM: 10,
}

interface MissionDraftState {
  farmPolygon: LngLat[] | null
  flightParams: FlightParams
  generated: GridResponse | null
  isGenerating: boolean
  generateError: string | null

  // Manual Mission Mode — an ordered, user-assembled mission-item list
  // (see types/mission-items.ts). Home is a separate reference point, never
  // a flown item, matching every mission format in this app's index-0
  // convention; "Launch" is manualItems[0] once placed — a takeoff-type
  // item — kept in sync by setManualLaunch, not a separate field.
  manualHome: LngLat | null
  manualItems: MissionItem[]

  setFarmPolygon: (polygon: LngLat[] | null) => void
  updateFlightParams: (patch: Partial<FlightParams>) => void
  applyServerDefaults: (defaults: Partial<FlightParams>) => void
  setGenerated: (result: GridResponse | null) => void
  setGenerating: (isGenerating: boolean) => void
  setGenerateError: (error: string | null) => void
  setManualHome: (position: LngLat | null) => void
  /** Bulk-replaces the whole item list — used to rehydrate a Mission
   * Library entry on redeploy, where every item (not just one) needs to be
   * set at once from the server's response. */
  setManualItems: (items: MissionItem[]) => void
  setManualLaunch: (position: LngLat) => void
  addManualWaypoint: (position: LngLat, altitude: number) => void
  /** Generic add for the full Mission Toolbox. Position is required for
   * the four positional types (takeoff/waypoint/loiter/land) and ignored
   * for rtl/change_speed, which have no map location. */
  addManualItem: (type: MissionItemType, position?: LngLat) => string
  updateManualItem: (id: string, patch: Partial<MissionItem>) => void
  moveManualItem: (id: string, position: LngLat) => void
  removeManualItem: (id: string) => void
  /** Clones an item (new id) and inserts the copy immediately after it. */
  duplicateManualItem: (id: string) => void
  /** Inserts a fresh default Waypoint immediately before/after the given
   * item — not a clone of the reference item's type, matching the common
   * mission-planner convention that "insert" adds a waypoint you then
   * drag into place, while "duplicate" copies the item you already have. */
  insertManualItemBefore: (id: string) => void
  insertManualItemAfter: (id: string) => void
  moveManualItemUp: (id: string) => void
  moveManualItemDown: (id: string) => void
  clearManualMission: () => void
  reset: () => void
}

const INITIAL_MANUAL_STATE = {
  manualHome: null as LngLat | null,
  manualItems: [] as MissionItem[],
}

export const useMissionDraftStore = create<MissionDraftState>((set) => ({
  farmPolygon: null,
  flightParams: DEFAULT_FLIGHT_PARAMS,
  generated: null,
  isGenerating: false,
  generateError: null,
  ...INITIAL_MANUAL_STATE,

  setFarmPolygon: (polygon) => set({ farmPolygon: polygon, generated: null }),
  updateFlightParams: (patch) =>
    set((s) => ({ flightParams: { ...s.flightParams, ...patch } })),
  applyServerDefaults: (defaults) =>
    set((s) => ({ flightParams: { ...s.flightParams, ...defaults } })),
  setGenerated: (result) => set({ generated: result }),
  setGenerating: (isGenerating) => set({ isGenerating }),
  setGenerateError: (error) => set({ generateError: error }),
  setManualHome: (position) => set({ manualHome: position, generated: null }),
  setManualItems: (items) => set({ manualItems: items, generated: null }),

  // Finds-or-inserts the takeoff item at position 0 rather than keeping a
  // separate "launch" field — the item list is the single source of truth
  // for order, per Phase 2A's foundation for a future full item toolbox.
  setManualLaunch: (position) =>
    set((s) => {
      const existing = s.manualItems.find((it): it is TakeoffItem => it.type === 'takeoff')
      if (existing) {
        return {
          manualItems: s.manualItems.map((it) =>
            it.id === existing.id ? { ...it, lat: position[1], lng: position[0] } : it,
          ),
          generated: null,
        }
      }
      const takeoff: TakeoffItem = {
        id: createItemId(),
        type: 'takeoff',
        lat: position[1],
        lng: position[0],
        altitude: s.flightParams.altitudeM,
      }
      return { manualItems: [takeoff, ...s.manualItems], generated: null }
    }),

  addManualWaypoint: (position, altitude) =>
    set((s) => ({
      manualItems: [
        ...s.manualItems,
        { id: createItemId(), type: 'waypoint', lat: position[1], lng: position[0], altitude },
      ],
      generated: null,
    })),

  // Toolbox entry point for all 6 item types. Takeoff reuses setManualLaunch's
  // find-or-update semantics (there is only ever one takeoff item); RTL and
  // Change Speed have no map position, so they're appended immediately
  // rather than waiting for a map click. Returns the new item's id so the
  // caller (the toolbox) can select it right away — necessary for RTL/
  // Change Speed, which have no marker to click afterward.
  addManualItem: (type, position) => {
    const id = createItemId()
    set((s) => {
      switch (type) {
        case 'takeoff': {
          const existing = s.manualItems.find((it): it is TakeoffItem => it.type === 'takeoff')
          if (existing) {
            if (!position) return {}
            return {
              manualItems: s.manualItems.map((it) =>
                it.id === existing.id ? { ...it, lat: position[1], lng: position[0] } : it,
              ),
              generated: null,
            }
          }
          const takeoff: TakeoffItem = {
            id, type: 'takeoff',
            lat: position ? position[1] : (s.manualHome?.[1] ?? 0),
            lng: position ? position[0] : (s.manualHome?.[0] ?? 0),
            altitude: s.flightParams.altitudeM,
          }
          return { manualItems: [takeoff, ...s.manualItems], generated: null }
        }
        case 'waypoint': {
          if (!position) return {}
          const item: WaypointItem = {
            id, type: 'waypoint', lat: position[1], lng: position[0], altitude: s.flightParams.altitudeM,
          }
          return { manualItems: [...s.manualItems, item], generated: null }
        }
        case 'loiter': {
          if (!position) return {}
          const item: LoiterItem = {
            id, type: 'loiter', lat: position[1], lng: position[0],
            altitude: s.flightParams.altitudeM, holdTimeS: s.flightParams.holdTimeS,
          }
          return { manualItems: [...s.manualItems, item], generated: null }
        }
        case 'land': {
          if (!position) return {}
          const item: LandItem = { id, type: 'land', lat: position[1], lng: position[0] }
          return { manualItems: [...s.manualItems, item], generated: null }
        }
        case 'rtl': {
          const item: RtlItem = { id, type: 'rtl' }
          return { manualItems: [...s.manualItems, item], generated: null }
        }
        case 'change_speed': {
          const item: ChangeSpeedItem = { id, type: 'change_speed', speedMs: s.flightParams.speedMs }
          return { manualItems: [...s.manualItems, item], generated: null }
        }
        default:
          return {}
      }
    })
    return id
  },

  updateManualItem: (id, patch) =>
    set((s) => ({
      manualItems: s.manualItems.map((it) => (it.id === id ? ({ ...it, ...patch } as MissionItem) : it)),
      generated: null,
    })),

  moveManualItem: (id, position) =>
    set((s) => ({
      manualItems: s.manualItems.map((it) =>
        it.id === id && 'lat' in it ? { ...it, lat: position[1], lng: position[0] } : it,
      ),
      generated: null,
    })),

  removeManualItem: (id) =>
    set((s) => ({
      manualItems: s.manualItems.filter((it) => it.id !== id),
      generated: null,
    })),

  duplicateManualItem: (id) =>
    set((s) => {
      const index = s.manualItems.findIndex((it) => it.id === id)
      if (index === -1) return {}
      const copy: MissionItem = { ...s.manualItems[index], id: createItemId() }
      const manualItems = [...s.manualItems]
      manualItems.splice(index + 1, 0, copy)
      return { manualItems, generated: null }
    }),

  insertManualItemBefore: (id) =>
    set((s) => {
      const index = s.manualItems.findIndex((it) => it.id === id)
      if (index === -1) return {}
      const ref = s.manualItems[index]
      const item: WaypointItem = {
        id: createItemId(), type: 'waypoint',
        lat: hasPosition(ref) ? ref.lat : (s.manualHome?.[1] ?? 0),
        lng: hasPosition(ref) ? ref.lng : (s.manualHome?.[0] ?? 0),
        altitude: s.flightParams.altitudeM,
      }
      const manualItems = [...s.manualItems]
      manualItems.splice(index, 0, item)
      return { manualItems, generated: null }
    }),

  insertManualItemAfter: (id) =>
    set((s) => {
      const index = s.manualItems.findIndex((it) => it.id === id)
      if (index === -1) return {}
      const ref = s.manualItems[index]
      const item: WaypointItem = {
        id: createItemId(), type: 'waypoint',
        lat: hasPosition(ref) ? ref.lat : (s.manualHome?.[1] ?? 0),
        lng: hasPosition(ref) ? ref.lng : (s.manualHome?.[0] ?? 0),
        altitude: s.flightParams.altitudeM,
      }
      const manualItems = [...s.manualItems]
      manualItems.splice(index + 1, 0, item)
      return { manualItems, generated: null }
    }),

  moveManualItemUp: (id) =>
    set((s) => {
      const index = s.manualItems.findIndex((it) => it.id === id)
      if (index <= 0) return {}
      const manualItems = [...s.manualItems]
      ;[manualItems[index - 1], manualItems[index]] = [manualItems[index], manualItems[index - 1]]
      return { manualItems, generated: null }
    }),

  moveManualItemDown: (id) =>
    set((s) => {
      const index = s.manualItems.findIndex((it) => it.id === id)
      if (index === -1 || index >= s.manualItems.length - 1) return {}
      const manualItems = [...s.manualItems]
      ;[manualItems[index + 1], manualItems[index]] = [manualItems[index], manualItems[index + 1]]
      return { manualItems, generated: null }
    }),

  clearManualMission: () => set({ ...INITIAL_MANUAL_STATE, generated: null }),
  reset: () =>
    set({
      farmPolygon: null,
      flightParams: DEFAULT_FLIGHT_PARAMS,
      generated: null,
      isGenerating: false,
      generateError: null,
      ...INITIAL_MANUAL_STATE,
    }),
}))
