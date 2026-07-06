import { create } from 'zustand'

export type GeolocationStatus =
  | 'idle'
  | 'requesting'
  | 'granted'
  | 'denied'
  | 'unsupported'
  | 'insecure-context'
  | 'error'

export interface MyLocationFix {
  lat: number
  lng: number
  accuracy: number
}

interface GeolocationState {
  position: MyLocationFix | null
  status: GeolocationStatus
  errorMessage: string | null
  setPosition: (position: MyLocationFix) => void
  setStatus: (status: GeolocationStatus) => void
  setError: (message: string) => void
}

/** Single shared home for the browser's own GPS/location fix, populated by
 * the one `useMyLocation()` watcher mounted in `MyLocationMarker`. A store
 * (rather than local component state) lets sibling UI — the "Center on My
 * Location" button — read the latest fix without starting a second
 * `watchPosition` subscription. */
export const useGeolocationStore = create<GeolocationState>((set) => ({
  position: null,
  status: 'idle',
  errorMessage: null,
  setPosition: (position) => set({ position, status: 'granted', errorMessage: null }),
  setStatus: (status) => set({ status }),
  setError: (errorMessage) => set({ errorMessage, status: 'error' }),
}))
