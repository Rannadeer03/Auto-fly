import { createContext, useContext } from 'react'
import type maplibregl from 'maplibre-gl'

export const MapContext = createContext<maplibregl.Map | null>(null)

/** The live MapLibre map instance, or null before it has finished loading. */
export function useMapInstance(): maplibregl.Map | null {
  return useContext(MapContext)
}
