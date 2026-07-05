import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { generateSurveyMission, clearMission } from '@/services/mission-service'
import { useMissionDraftStore } from '@/store/mission-draft-store'
import { toBackendPolygon, longestEdgeAngleDeg } from '@/utils/geo'
import type { GridRequest } from '@/types/mission'

/** Re-generates the current survey with upload:true — same params the
 * live preview already validated, so what gets flown matches what was shown. */
export function useUploadMission() {
  const queryClient = useQueryClient()
  const setGenerated = useMissionDraftStore((s) => s.setGenerated)

  return useMutation({
    mutationFn: () => {
      const { farmPolygon, flightParams } = useMissionDraftStore.getState()
      if (!farmPolygon || farmPolygon.length < 3) {
        throw new Error('Draw a farm boundary before uploading.')
      }
      const angleDeg =
        flightParams.surveyDirection === 'auto'
          ? longestEdgeAngleDeg(farmPolygon)
          : flightParams.angleDeg

      const body: GridRequest = {
        polygon: toBackendPolygon(farmPolygon),
        altitude_m: flightParams.altitudeM,
        speed_ms: flightParams.speedMs,
        side_overlap_pct: flightParams.sideOverlapPct,
        front_overlap_pct: flightParams.frontOverlapPct,
        angle_deg: angleDeg,
        upload: true,
        capture_mode: flightParams.captureMode,
        hold_time_s: flightParams.holdTimeS,
        mission_name: flightParams.missionName || undefined,
        camera_angle_deg: flightParams.cameraAngleDeg,
      }
      return generateSurveyMission(body)
    },
    onSuccess: (res) => {
      setGenerated(res)
      if (res.uploaded_to_drone && res.verified) toast.success(res.message)
      else if (res.uploaded_to_drone) toast.warning(res.message)
      else toast.info(res.message)
      queryClient.invalidateQueries({ queryKey: ['mission-status'] })
      queryClient.invalidateQueries({ queryKey: ['telemetry'] })
    },
    onError: (err: Error) => toast.error(`Upload failed — ${err.message}`),
  })
}

export function useClearMission() {
  const queryClient = useQueryClient()
  const reset = useMissionDraftStore((s) => s.reset)

  return useMutation({
    mutationFn: clearMission,
    onSuccess: (res) => {
      if (res.success) toast.success(res.message)
      else toast.error(res.message)
      reset()
      queryClient.invalidateQueries({ queryKey: ['mission-status'] })
    },
    onError: (err: Error) => toast.error(`Clear failed — ${err.message}`),
  })
}
