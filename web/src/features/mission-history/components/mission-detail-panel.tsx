import { useState, type ReactNode } from 'react'
import { Download, Trash2, ScrollText, X, MapPin, Compass, Gauge, Satellite } from 'lucide-react'
import { Panel, PanelBody, PanelHeader, PanelTitle } from '@/components/ui/panel'
import { Button } from '@/components/ui/button'
import { StatTile } from '@/components/ui/stat-tile'
import { ConfirmDialog } from '@/components/feedback/confirm-dialog'
import { MissionReplayMap } from '@/features/mission-history/components/mission-replay-map'
import { useMissionDetail, useMissionLog, useDeleteMission } from '@/features/mission-history/hooks/use-missions'
import { missionDownloadUrl, missionImageUrl, missionThumbnailUrl } from '@/services/mission-history-service'
import { formatBytes, formatDistance, formatTimestamp } from '@/utils/format'
import type { ImageMetadata } from '@/types/mission-history'
import { cn } from '@/utils/cn'

interface MissionDetailPanelProps {
  name: string
  onClose: () => void
  onDeleted: () => void
}

export function MissionDetailPanel({ name, onClose, onDeleted }: MissionDetailPanelProps) {
  const { data: detail, isLoading } = useMissionDetail(name)
  const [showLog, setShowLog] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [selectedImage, setSelectedImage] = useState<ImageMetadata | null>(null)
  const { data: log } = useMissionLog(name, showLog)
  const del = useDeleteMission()

  if (isLoading || !detail) {
    return (
      <Panel className="flex h-full items-center justify-center">
        <p className="text-xs text-text-tertiary">Loading mission…</p>
      </Panel>
    )
  }

  const meta = detail.metadata
  const images = detail.images ?? []

  const selectImage = (filename: string) => {
    setSelectedImage(images.find((img) => img.filename === filename) ?? null)
  }

  return (
    <Panel className="flex h-full flex-col overflow-hidden">
      <PanelHeader>
        <div className="min-w-0">
          <PanelTitle className="truncate normal-case tracking-normal text-sm text-text-primary">
            {meta?.mission_name || detail.name}
          </PanelTitle>
          <p className="text-[11px] text-text-tertiary">{formatTimestamp(meta?.started_at)}</p>
        </div>
        <div className="flex items-center gap-1.5">
          <Button size="icon" variant="ghost" onClick={() => setShowLog((v) => !v)} title="View log">
            <ScrollText className="h-4 w-4" />
          </Button>
          <Button size="icon" variant="ghost" asChild title="Download ZIP">
            <a href={missionDownloadUrl(detail.name)} download>
              <Download className="h-4 w-4" />
            </a>
          </Button>
          <Button
            size="icon"
            variant="ghost"
            disabled={detail.active}
            title={detail.active ? 'Still recording' : 'Delete mission'}
            onClick={() => setConfirmDelete(true)}
          >
            <Trash2 className="h-4 w-4 text-danger-500" />
          </Button>
          <Button size="icon" variant="ghost" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
      </PanelHeader>

      <PanelBody className="flex-1 space-y-4 overflow-y-auto">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <StatTile label="Images" value={String(detail.photo_count)} />
          <StatTile label="Distance" value={detail.stats ? formatDistance(detail.stats.distance_m) : '—'} />
          <StatTile label="Max alt." value={detail.stats ? `${detail.stats.max_altitude_rel_m.toFixed(0)} m` : '—'} />
          <StatTile label="Size" value={formatBytes(detail.total_size_bytes)} />
        </div>

        {(meta?.end_reason || (meta?.failed_captures ?? 0) > 0) && (
          <div className="space-y-1.5">
            {meta?.end_reason && (
              <p className="rounded-[var(--radius-control)] bg-surface-3 px-3 py-2 text-xs text-text-secondary">
                Ended: {meta.end_reason}
              </p>
            )}
            {(meta?.failed_captures ?? 0) > 0 && (
              <p className="rounded-[var(--radius-control)] bg-warning-500/10 px-3 py-2 text-xs text-warning-500">
                {meta!.failed_captures} capture attempt(s) failed during this mission (logged, mission continued).
              </p>
            )}
          </div>
        )}

        {showLog ? (
          <div className="h-64 overflow-y-auto rounded-[var(--radius-control)] bg-canvas p-3 font-mono text-[11px] leading-relaxed text-text-secondary">
            {(log?.lines ?? []).map((line, i) => (
              <div key={i}>{line}</div>
            ))}
            {!log?.lines.length && <span className="text-text-tertiary">No log entries.</span>}
          </div>
        ) : (
          <div className="h-72">
            <MissionReplayMap
              images={images}
              selectedFilename={selectedImage?.filename ?? null}
              onSelectImage={selectImage}
            />
          </div>
        )}

        {selectedImage && (
          <div className="rounded-[var(--radius-control)] border border-accent-500/30 bg-surface-3 p-3">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs font-semibold text-text-primary">
                Waypoint {selectedImage.waypoint_number} · Capture #{selectedImage.capture_sequence}
              </span>
              <button onClick={() => setSelectedImage(null)} className="text-text-tertiary hover:text-text-primary">
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
            <img
              src={missionImageUrl(detail.name, selectedImage.filename)}
              alt={`Capture at waypoint ${selectedImage.waypoint_number}`}
              className="mb-3 max-h-64 w-full rounded-[6px] object-contain"
            />
            <div className="grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-4">
              <MetaField icon={<MapPin className="h-3 w-3" />} label="Position">
                {selectedImage.latitude.toFixed(6)}, {selectedImage.longitude.toFixed(6)}
              </MetaField>
              <MetaField icon={<Compass className="h-3 w-3" />} label="Heading">
                {selectedImage.heading_deg.toFixed(0)}°
              </MetaField>
              <MetaField icon={<Gauge className="h-3 w-3" />} label="Speed">
                {selectedImage.drone_speed_ms.toFixed(1)} m/s
              </MetaField>
              <MetaField icon={<Satellite className="h-3 w-3" />} label="GPS">
                {selectedImage.gps_fix_quality} · {selectedImage.satellites_visible} sats
              </MetaField>
              <MetaField label="Altitude">{selectedImage.altitude_rel.toFixed(1)} m</MetaField>
              <MetaField label="Pitch / Roll">
                {selectedImage.pitch_deg.toFixed(1)}° / {selectedImage.roll_deg.toFixed(1)}°
              </MetaField>
              <MetaField label="Camera angle">{selectedImage.camera_orientation_deg}°</MetaField>
              <MetaField label="Captured">{formatTimestamp(selectedImage.timestamp)}</MetaField>
            </div>
          </div>
        )}

        {images.length > 0 && (
          <div>
            <p className="mb-2 text-xs font-medium text-text-secondary">
              Captured images ({images.length})
            </p>
            <div className="grid grid-cols-4 gap-2 sm:grid-cols-6">
              {images.map((image) => (
                <button
                  key={image.filename}
                  onClick={() => selectImage(image.filename)}
                  className={cn(
                    'aspect-square overflow-hidden rounded-[6px] ring-2 ring-transparent transition-all hover:ring-accent-500/50',
                    selectedImage?.filename === image.filename && 'ring-accent-500',
                  )}
                >
                  <img
                    src={missionThumbnailUrl(detail.name, image.filename)}
                    loading="lazy"
                    className="h-full w-full object-cover"
                    alt={`Waypoint ${image.waypoint_number} capture`}
                  />
                </button>
              ))}
            </div>
          </div>
        )}
      </PanelBody>

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={`Delete "${detail.name}"?`}
        description="This permanently removes the mission folder — images, video, telemetry, metadata, and logs. This cannot be undone."
        confirmLabel="Delete permanently"
        onConfirm={() => del.mutate(detail.name, { onSuccess: onDeleted })}
      />
    </Panel>
  )
}

function MetaField({
  icon,
  label,
  children,
}: {
  icon?: ReactNode
  label: string
  children: ReactNode
}) {
  return (
    <div>
      <div className="flex items-center gap-1 text-text-tertiary">
        {icon}
        {label}
      </div>
      <div className="font-mono text-text-primary">{children}</div>
    </div>
  )
}
