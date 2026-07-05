import { useState } from 'react'
import { Camera, CameraOff, Circle, Square, ImageOff } from 'lucide-react'
import { Panel, PanelBody, PanelHeader, PanelTitle } from '@/components/ui/panel'
import { StatTile } from '@/components/ui/stat-tile'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { useCameraStatus, useCapturePhoto, useToggleRecording } from '@/features/camera/hooks/use-camera'
import { captureFileUrl } from '@/services/camera-service'

export function CameraPage() {
  const { data, isError } = useCameraStatus()
  const capture = useCapturePhoto()
  const [lastCaptureUrl, setLastCaptureUrl] = useState<string | null>(null)

  const recording = data?.recording.recording ?? false
  const toggleRecording = useToggleRecording(recording)

  const camera = data?.camera

  return (
    <div className="mx-auto max-w-3xl space-y-4 p-6">
      <Panel>
        <PanelHeader>
          <PanelTitle>Camera</PanelTitle>
          {camera?.healthy ? (
            <Badge variant="success" dot>
              Healthy
            </Badge>
          ) : (
            <Badge variant="danger" dot>
              {isError ? 'Unreachable' : 'Disconnected'}
            </Badge>
          )}
        </PanelHeader>
        <PanelBody>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <StatTile label="Device" value={camera?.device ?? '—'} />
            <StatTile label="Resolution" value={camera ? `${camera.configured_width}×${camera.configured_height}` : '—'} />
            <StatTile label="Measured FPS" value={camera ? camera.measured_fps.toFixed(1) : '—'} />
            <StatTile
              label="Last frame"
              value={
                camera?.last_frame_age_seconds != null
                  ? `${camera.last_frame_age_seconds.toFixed(1)}s ago`
                  : '—'
              }
              tone={
                camera?.last_frame_age_seconds != null && camera.last_frame_age_seconds > 3
                  ? 'warning'
                  : 'default'
              }
            />
          </div>

          <div className="mt-4 flex items-center gap-2">
            <Button
              variant="outline"
              disabled={!camera?.healthy || capture.isPending}
              onClick={() =>
                capture.mutate(undefined, {
                  onSuccess: (res) => {
                    const path = (res.data as { path?: string } | undefined)?.path
                    if (path) setLastCaptureUrl(captureFileUrl(path))
                  },
                })
              }
            >
              <Camera className="h-4 w-4" />
              Capture Photo
            </Button>
            <Button
              variant={recording ? 'danger' : 'outline'}
              disabled={!camera?.healthy || toggleRecording.isPending}
              onClick={() => toggleRecording.mutate()}
            >
              {recording ? <Square className="h-4 w-4" /> : <Circle className="h-4 w-4" />}
              {recording ? 'Stop Recording' : 'Start Recording'}
            </Button>
          </div>
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader>
          <PanelTitle>Last Manual Capture</PanelTitle>
        </PanelHeader>
        <PanelBody>
          {lastCaptureUrl ? (
            <img
              src={lastCaptureUrl}
              alt="Last manual capture"
              className="max-h-96 w-full rounded-[var(--radius-control)] object-contain"
            />
          ) : (
            <div className="flex h-48 flex-col items-center justify-center gap-2 rounded-[var(--radius-control)] bg-surface-3 text-text-tertiary">
              {camera?.healthy ? <ImageOff className="h-6 w-6" /> : <CameraOff className="h-6 w-6" />}
              <span className="text-xs">No manual capture this session</span>
            </div>
          )}
        </PanelBody>
      </Panel>
    </div>
  )
}
