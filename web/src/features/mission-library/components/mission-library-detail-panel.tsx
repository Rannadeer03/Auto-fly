import { useState, type ReactNode } from 'react'
import { Copy, Download, Pencil, Trash2, UploadCloud, X } from 'lucide-react'
import { Panel, PanelBody, PanelHeader, PanelTitle } from '@/components/ui/panel'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input, Textarea } from '@/components/ui/input'
import { StatTile } from '@/components/ui/stat-tile'
import { ConfirmDialog } from '@/components/feedback/confirm-dialog'
import {
  useDeleteLibraryEntry,
  useDeployLibraryEntry,
  useDuplicateLibraryEntry,
  useLibraryEntry,
  useRenameLibraryEntry,
} from '@/features/mission-library/hooks/use-mission-library'
import { libraryDownloadUrl } from '@/services/mission-library-service'
import type { SurveyLibraryParams } from '@/types/mission-library'
import { formatDistance, formatDuration, formatPercent, formatTimestamp } from '@/utils/format'

interface MissionLibraryDetailPanelProps {
  id: string
  onClose: () => void
  onDeleted: () => void
}

export function MissionLibraryDetailPanel({ id, onClose, onDeleted }: MissionLibraryDetailPanelProps) {
  const { data: entry, isLoading } = useLibraryEntry(id)
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(false)

  const rename = useRenameLibraryEntry()
  const duplicate = useDuplicateLibraryEntry()
  const del = useDeleteLibraryEntry()
  const deploy = useDeployLibraryEntry()

  if (isLoading || !entry) {
    return (
      <Panel className="flex h-full items-center justify-center">
        <p className="text-xs text-text-tertiary">Loading mission…</p>
      </Panel>
    )
  }

  const startEditing = () => {
    setName(entry.name)
    setDescription(entry.description)
    setEditing(true)
  }

  const saveEditing = () => {
    rename.mutate({ id: entry.id, name, description })
    setEditing(false)
  }

  return (
    <Panel className="flex h-full flex-col overflow-hidden">
      <PanelHeader>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <PanelTitle className="truncate normal-case tracking-normal text-sm text-text-primary">
              {entry.name}
            </PanelTitle>
            <Badge variant={entry.mode === 'manual' ? 'accent' : 'neutral'}>
              {entry.mode === 'manual' ? 'Manual' : 'Survey'}
            </Badge>
          </div>
          <p className="text-[11px] text-text-tertiary">Saved {formatTimestamp(entry.created_at)}</p>
        </div>
        <div className="flex items-center gap-1.5">
          <Button size="icon" variant="ghost" onClick={startEditing} title="Rename / edit description">
            <Pencil className="h-4 w-4" />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            onClick={() => duplicate.mutate(entry.id)}
            disabled={duplicate.isPending}
            title="Duplicate"
          >
            <Copy className="h-4 w-4" />
          </Button>
          <Button size="icon" variant="ghost" asChild title="Download .plan (QGroundControl-compatible)">
            <a href={libraryDownloadUrl(entry.id)} download>
              <Download className="h-4 w-4" />
            </a>
          </Button>
          <Button
            size="icon"
            variant="ghost"
            title="Delete permanently"
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
        {editing ? (
          <div className="space-y-2">
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Mission name" />
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Description"
              rows={3}
            />
            <div className="flex justify-end gap-2">
              <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>
                Cancel
              </Button>
              <Button size="sm" variant="accent" onClick={saveEditing} disabled={rename.isPending}>
                Save
              </Button>
            </div>
          </div>
        ) : (
          entry.description && <p className="text-sm text-text-secondary">{entry.description}</p>
        )}

        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <StatTile label="Waypoints" value={String(entry.waypoint_count)} />
          <StatTile label="Distance" value={formatDistance(entry.total_distance_km * 1000)} />
          <StatTile label="Duration" value={formatDuration(entry.estimated_duration_minutes)} />
          <StatTile label="Battery" value={formatPercent(entry.estimated_battery_percent)} />
        </div>

        {entry.mode === 'manual' ? (
          <div className="grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-3">
            <MetaField label="Speed">{entry.params.speed_ms} m/s</MetaField>
          </div>
        ) : (
          (() => {
            const params = entry.params as SurveyLibraryParams
            return (
              <div className="grid grid-cols-2 gap-2 text-[11px] sm:grid-cols-3">
                <MetaField label="Altitude">{params.altitude_m} m</MetaField>
                <MetaField label="Speed">{params.speed_ms} m/s</MetaField>
                <MetaField label="Side overlap">{params.side_overlap_pct}%</MetaField>
                <MetaField label="Front overlap">{params.front_overlap_pct}%</MetaField>
                <MetaField label="Grid angle">{params.angle_deg}°</MetaField>
                <MetaField label="Capture mode">{params.capture_mode}</MetaField>
              </div>
            )
          })()
        )}

        <Button
          className="w-full"
          variant="accent"
          onClick={() => deploy.mutate(entry.id)}
          disabled={deploy.isPending}
        >
          <UploadCloud className="h-4 w-4" />
          Upload to Drone Again
        </Button>
      </PanelBody>

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={`Delete "${entry.name}"?`}
        description="This permanently removes the saved mission plan from the library. This cannot be undone."
        confirmLabel="Delete permanently"
        onConfirm={() => del.mutate(entry.id, { onSuccess: onDeleted })}
      />
    </Panel>
  )
}

function MetaField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div className="text-text-tertiary">{label}</div>
      <div className="font-mono text-text-primary">{children}</div>
    </div>
  )
}
