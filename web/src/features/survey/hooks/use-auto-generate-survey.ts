import { useEffect, useRef } from 'react'
import { useMutation } from '@tanstack/react-query'
import { generateSurveyMission } from '@/services/mission-service'
import { useMissionDraftStore } from '@/store/mission-draft-store'
import { toBackendPolygon, longestEdgeAngleDeg, polygonAreaM2 } from '@/utils/geo'
import { SURVEY_REGENERATE_DEBOUNCE_MS } from '@/constants/api'
import type { GridRequest } from '@/types/mission'

const MIN_FARM_AREA_M2 = 4 // guards against a mis-drawn sliver polygon

/**
 * Regenerates the survey (preview only, upload:false) whenever the drawn
 * farm boundary or any flight parameter changes, debounced so a dragged
 * slider doesn't fire a request per pixel. This is what makes the map,
 * waypoint list, and estimation panel all "live" per the product spec.
 */
export function useAutoGenerateSurvey() {
  const farmPolygon = useMissionDraftStore((s) => s.farmPolygon)
  const flightParams = useMissionDraftStore((s) => s.flightParams)
  const setGenerated = useMissionDraftStore((s) => s.setGenerated)
  const setGenerating = useMissionDraftStore((s) => s.setGenerating)
  const setGenerateError = useMissionDraftStore((s) => s.setGenerateError)

  const mutation = useMutation({
    mutationFn: (body: GridRequest) => generateSurveyMission(body),
  })
  const timerRef = useRef<number | null>(null)

  useEffect(() => {
    if (!farmPolygon || farmPolygon.length < 3 || polygonAreaM2(farmPolygon) < MIN_FARM_AREA_M2) {
      setGenerated(null)
      setGenerateError(null)
      setGenerating(false)
      return
    }

    if (timerRef.current !== null) window.clearTimeout(timerRef.current)
    setGenerating(true)

    const angleDeg =
      flightParams.surveyDirection === 'auto'
        ? longestEdgeAngleDeg(farmPolygon)
        : flightParams.angleDeg

    timerRef.current = window.setTimeout(() => {
      const body: GridRequest = {
        polygon: toBackendPolygon(farmPolygon),
        altitude_m: flightParams.altitudeM,
        speed_ms: flightParams.speedMs,
        side_overlap_pct: flightParams.sideOverlapPct,
        front_overlap_pct: flightParams.frontOverlapPct,
        angle_deg: angleDeg,
        upload: false,
        capture_mode: flightParams.captureMode,
        hold_time_s: flightParams.holdTimeS,
        mission_name: flightParams.missionName || undefined,
        camera_angle_deg: flightParams.cameraAngleDeg,
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
  }, [farmPolygon, flightParams, setGenerated, setGenerating, setGenerateError])

  return mutation
}
