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

interface MissionDraftState {
  farmPolygon: LngLat[] | null
  flightParams: FlightParams
  generated: GridResponse | null
  isGenerating: boolean
  generateError: string | null

  setFarmPolygon: (polygon: LngLat[] | null) => void
  updateFlightParams: (patch: Partial<FlightParams>) => void
  applyServerDefaults: (defaults: Partial<FlightParams>) => void
  setGenerated: (result: GridResponse | null) => void
  setGenerating: (isGenerating: boolean) => void
  setGenerateError: (error: string | null) => void
  reset: () => void
}

export const useMissionDraftStore = create<MissionDraftState>((set) => ({
  farmPolygon: null,
  flightParams: DEFAULT_FLIGHT_PARAMS,
  generated: null,
  isGenerating: false,
  generateError: null,

  setFarmPolygon: (polygon) => set({ farmPolygon: polygon, generated: null }),
  updateFlightParams: (patch) =>
    set((s) => ({ flightParams: { ...s.flightParams, ...patch } })),
  applyServerDefaults: (defaults) =>
    set((s) => ({ flightParams: { ...s.flightParams, ...defaults } })),
  setGenerated: (result) => set({ generated: result }),
  setGenerating: (isGenerating) => set({ isGenerating }),
  setGenerateError: (error) => set({ generateError: error }),
  reset: () =>
    set({
      farmPolygon: null,
      flightParams: DEFAULT_FLIGHT_PARAMS,
      generated: null,
      isGenerating: false,
      generateError: null,
    }),
}))
