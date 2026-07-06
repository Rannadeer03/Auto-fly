import { useEffect, useRef } from 'react'
import { useMutation } from '@tanstack/react-query'
import { generateManualMission } from '@/services/mission-service'
import { useMissionDraftStore } from '@/store/mission-draft-store'
import { SURVEY_REGENERATE_DEBOUNCE_MS } from '@/constants/api'
import type { ManualMissionRequest } from '@/types/mission'

/**
 * Manual Mission Mode's counterpart to features/survey/hooks/use-auto-generate-survey.ts
 * — regenerates a preview (upload:false) whenever Launch/Home/waypoints/speed
 * change, debounced so a drag gesture doesn't fire a request per pixel.
 * Requires both Launch and Home placed plus at least one waypoint; until
 * then it just clears any stale preview.
 */
export function useGenerateManualMission() {
  const manualLaunch = useMissionDraftStore((s) => s.manualLaunch)
  const manualHome = useMissionDraftStore((s) => s.manualHome)
  const manualWaypoints = useMissionDraftStore((s) => s.manualWaypoints)
  const speedMs = useMissionDraftStore((s) => s.flightParams.speedMs)
  const missionName = useMissionDraftStore((s) => s.flightParams.missionName)
  const setGenerated = useMissionDraftStore((s) => s.setGenerated)
  const setGenerating = useMissionDraftStore((s) => s.setGenerating)
  const setGenerateError = useMissionDraftStore((s) => s.setGenerateError)

  const mutation = useMutation({
    mutationFn: (body: ManualMissionRequest) => generateManualMission(body),
  })
  const timerRef = useRef<number | null>(null)

  useEffect(() => {
    if (!manualLaunch || !manualHome || manualWaypoints.length < 1) {
      setGenerated(null)
      setGenerateError(null)
      setGenerating(false)
      return
    }

    if (timerRef.current !== null) window.clearTimeout(timerRef.current)
    setGenerating(true)

    timerRef.current = window.setTimeout(() => {
      const body: ManualMissionRequest = {
        launch: manualLaunch,
        home: manualHome,
        waypoints: manualWaypoints.map((w) => ({ lat: w.lat, lon: w.lng, altitude_m: w.altitude })),
        speed_ms: speedMs,
        upload: false,
        mission_name: missionName || undefined,
      }
      mutation.mutate(body, {
        onSuccess: (res) => {
          setGenerated(res)
          setGenerateError(res.success ? null : res.message)
        },
        onError: (err: Error) => {
          setGenerated(null)
          setGenerateError(err.message)
        },
        onSettled: () => setGenerating(false),
      })
    }, SURVEY_REGENERATE_DEBOUNCE_MS)

    return () => {
      if (timerRef.current !== null) window.clearTimeout(timerRef.current)
    }
    // mutation is stable from useMutation and intentionally excluded — including
    // it would re-run this effect on every mutation state change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [manualLaunch, manualHome, manualWaypoints, speedMs, missionName, setGenerated, setGenerating, setGenerateError])

  return mutation
}
