import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { CAMERA_STATUS_POLL_MS } from '@/constants/api'
import { capturePhoto, fetchCameraStatus, startRecording, stopRecording } from '@/services/camera-service'

export function useCameraStatus() {
  return useQuery({
    queryKey: ['camera-status'],
    queryFn: ({ signal }) => fetchCameraStatus(signal),
    refetchInterval: CAMERA_STATUS_POLL_MS,
    retry: false,
  })
}

export function useCapturePhoto() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: capturePhoto,
    onSuccess: (res) => {
      if (res.success) toast.success('Photo captured')
      else toast.error(res.message)
      queryClient.invalidateQueries({ queryKey: ['camera-status'] })
    },
    onError: (err: Error) => toast.error(`Capture failed — ${err.message}`),
  })
}

export function useToggleRecording(isRecording: boolean) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => (isRecording ? stopRecording() : startRecording()),
    onSuccess: (res) => {
      if (res.success) toast.success(res.message)
      else toast.error(res.message)
      queryClient.invalidateQueries({ queryKey: ['camera-status'] })
    },
    onError: (err: Error) => toast.error(`Recording toggle failed — ${err.message}`),
  })
}
