import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { generateManualMission } from '@/services/mission-service'
import { useMissionDraftStore } from '@/store/mission-draft-store'
import type { ManualMissionRequest } from '@/types/mission'

/** Manual Mission Mode's counterpart to
 * features/mission-execution/hooks/use-upload-mission.ts's useUploadMission
 * — re-generates with upload:true so what gets flown matches the preview. */
export function useUploadManualMission() {
  const queryClient = useQueryClient()
  const setGenerated = useMissionDraftStore((s) => s.setGenerated)

  return useMutation({
    mutationFn: () => {
      const { manualLaunch, manualHome, manualWaypoints, flightParams } =
        useMissionDraftStore.getState()
      if (!manualLaunch || !manualHome) {
        throw new Error('Place a Launch and Home marker before uploading.')
      }
      if (manualWaypoints.length < 1) {
        throw new Error('Add at least one waypoint before uploading.')
      }
      const body: ManualMissionRequest = {
        launch: manualLaunch,
        home: manualHome,
        waypoints: manualWaypoints.map((w) => ({ lat: w.lat, lon: w.lng, altitude_m: w.altitude })),
        speed_ms: flightParams.speedMs,
        upload: true,
        mission_name: flightParams.missionName || undefined,
      }
      return generateManualMission(body)
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
