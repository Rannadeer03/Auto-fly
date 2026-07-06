import { create } from 'zustand'
import type { CaptureMode, GridResponse } from '@/types/mission'
import { createItemId, type MissionItem, type TakeoffItem } from '@/types/mission-items'

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
  updateManualItem: (id: string, patch: Partial<MissionItem>) => void
  moveManualItem: (id: string, position: LngLat) => void
  removeManualItem: (id: string) => void
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
