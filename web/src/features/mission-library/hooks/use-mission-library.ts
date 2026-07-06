import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  deleteLibraryEntry,
  deployLibraryEntry,
  duplicateLibraryEntry,
  fetchLibraryEntry,
  listLibrary,
  renameLibraryEntry,
  saveToLibrary,
} from '@/services/mission-library-service'
import { useMissionDraftStore } from '@/store/mission-draft-store'
import { useUiStore } from '@/store/ui-store'
import { toBackendPolygon, longestEdgeAngleDeg } from '@/utils/geo'
import type { SaveToLibraryRequest } from '@/types/mission-library'

const LIBRARY_KEY = ['mission-library']

export function useLibraryList(query: string) {
  return useQuery({
    queryKey: [...LIBRARY_KEY, query],
    queryFn: ({ signal }) => listLibrary(query, signal),
  })
}

export function useLibraryEntry(id: string | null) {
  return useQuery({
    queryKey: [...LIBRARY_KEY, 'detail', id],
    queryFn: ({ signal }) => fetchLibraryEntry(id as string, signal),
    enabled: id !== null,
  })
}

/** Saves the currently drawn survey (farm boundary + flight params) as a
 * reusable library entry — the server regenerates the mission from these
 * inputs itself, the same way the live preview does. */
export function useSaveToLibrary() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (vars: { name: string; description: string }) => {
      const { farmPolygon, flightParams } = useMissionDraftStore.getState()
      if (!farmPolygon || farmPolygon.length < 3) {
        throw new Error('Draw a farm boundary before saving to the library.')
      }
      const angleDeg =
        flightParams.surveyDirection === 'auto'
          ? longestEdgeAngleDeg(farmPolygon)
          : flightParams.angleDeg

      const body: SaveToLibraryRequest = {
        name: vars.name,
        description: vars.description,
        polygon: toBackendPolygon(farmPolygon),
        altitude_m: flightParams.altitudeM,
        speed_ms: flightParams.speedMs,
        side_overlap_pct: flightParams.sideOverlapPct,
        front_overlap_pct: flightParams.frontOverlapPct,
        angle_deg: angleDeg,
        capture_mode: flightParams.captureMode,
        hold_time_s: flightParams.holdTimeS,
        camera_angle_deg: flightParams.cameraAngleDeg,
      }
      return saveToLibrary(body)
    },
    onSuccess: (res) => {
      toast.success(res.message)
      queryClient.invalidateQueries({ queryKey: LIBRARY_KEY })
    },
    onError: (err: Error) => toast.error(`Save to library failed — ${err.message}`),
  })
}

export function useRenameLibraryEntry() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (vars: { id: string; name?: string; description?: string }) =>
      renameLibraryEntry(vars.id, { name: vars.name, description: vars.description }),
    onSuccess: () => {
      toast.success('Mission renamed.')
      queryClient.invalidateQueries({ queryKey: LIBRARY_KEY })
    },
    onError: (err: Error) => toast.error(`Rename failed — ${err.message}`),
  })
}

export function useDuplicateLibraryEntry() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => duplicateLibraryEntry(id),
    onSuccess: (entry) => {
      toast.success(`Duplicated as '${entry.name}'.`)
      queryClient.invalidateQueries({ queryKey: LIBRARY_KEY })
    },
    onError: (err: Error) => toast.error(`Duplicate failed — ${err.message}`),
  })
}

export function useDeleteLibraryEntry() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteLibraryEntry(id),
    onSuccess: (res) => {
      toast.success(res.message)
      queryClient.invalidateQueries({ queryKey: LIBRARY_KEY })
    },
    onError: (err: Error) => toast.error(`Delete failed — ${err.message}`),
  })
}

/** Uploads a saved plan straight to the connected drone, then loads it into
 * the mission-draft store and switches to the Mission map so the operator
 * sees exactly what was deployed. Never blocked by verification failing. */
export function useDeployLibraryEntry() {
  const queryClient = useQueryClient()
  const setFarmPolygon = useMissionDraftStore((s) => s.setFarmPolygon)
  const updateFlightParams = useMissionDraftStore((s) => s.updateFlightParams)
  const setGenerated = useMissionDraftStore((s) => s.setGenerated)
  const setActiveSection = useUiStore((s) => s.setActiveSection)

  return useMutation({
    mutationFn: (id: string) => deployLibraryEntry(id),
    onSuccess: (res) => {
      if (res.uploaded_to_drone && res.verified) toast.success(res.message)
      else if (res.uploaded_to_drone) toast.warning(res.message)
      else toast.info(res.message)

      updateFlightParams({
        altitudeM: res.params.altitude_m,
        speedMs: res.params.speed_ms,
        sideOverlapPct: res.params.side_overlap_pct,
        frontOverlapPct: res.params.front_overlap_pct,
        angleDeg: res.params.angle_deg,
        captureMode: res.params.capture_mode,
        holdTimeS: res.params.hold_time_s,
        cameraAngleDeg: res.params.camera_angle_deg,
      })
      setFarmPolygon(res.polygon.map(([lat, lng]) => [lng, lat]))
      setGenerated(res)
      setActiveSection('mission')

      queryClient.invalidateQueries({ queryKey: ['mission-status'] })
      queryClient.invalidateQueries({ queryKey: ['telemetry'] })
    },
    onError: (err: Error) => toast.error(`Deploy failed — ${err.message}`),
  })
}
