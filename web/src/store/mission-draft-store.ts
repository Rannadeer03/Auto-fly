import { create } from 'zustand'
import type { CaptureMode, GridResponse } from '@/types/mission'

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

export interface ManualWaypointDraft {
  lat: number
  lng: number
  altitude: number
}

interface MissionDraftState {
  farmPolygon: LngLat[] | null
  flightParams: FlightParams
  generated: GridResponse | null
  isGenerating: boolean
  generateError: string | null

  // Manual Mission Mode — an ordered, user-placed path. Launch/Home are each
  // a single marker (placing a new one replaces the old); waypoints are
  // append-only via addManualWaypoint (click order is never reordered).
  manualLaunch: LngLat | null
  manualHome: LngLat | null
  manualWaypoints: ManualWaypointDraft[]

  setFarmPolygon: (polygon: LngLat[] | null) => void
  updateFlightParams: (patch: Partial<FlightParams>) => void
  applyServerDefaults: (defaults: Partial<FlightParams>) => void
  setGenerated: (result: GridResponse | null) => void
  setGenerating: (isGenerating: boolean) => void
  setGenerateError: (error: string | null) => void
  setManualLaunch: (position: LngLat | null) => void
  setManualHome: (position: LngLat | null) => void
  addManualWaypoint: (waypoint: ManualWaypointDraft) => void
  updateManualWaypoint: (index: number, patch: Partial<ManualWaypointDraft>) => void
  moveManualWaypoint: (index: number, position: LngLat) => void
  removeManualWaypoint: (index: number) => void
  clearManualMission: () => void
  reset: () => void
}

const INITIAL_MANUAL_STATE = {
  manualLaunch: null as LngLat | null,
  manualHome: null as LngLat | null,
  manualWaypoints: [] as ManualWaypointDraft[],
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
  setManualLaunch: (position) => set({ manualLaunch: position, generated: null }),
  setManualHome: (position) => set({ manualHome: position, generated: null }),
  addManualWaypoint: (waypoint) =>
    set((s) => ({ manualWaypoints: [...s.manualWaypoints, waypoint], generated: null })),
  updateManualWaypoint: (index, patch) =>
    set((s) => ({
      manualWaypoints: s.manualWaypoints.map((w, i) => (i === index ? { ...w, ...patch } : w)),
      generated: null,
    })),
  moveManualWaypoint: (index, position) =>
    set((s) => ({
      manualWaypoints: s.manualWaypoints.map((w, i) =>
        i === index ? { ...w, lat: position[1], lng: position[0] } : w,
      ),
      generated: null,
    })),
  removeManualWaypoint: (index) =>
    set((s) => ({
      manualWaypoints: s.manualWaypoints.filter((_, i) => i !== index),
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
