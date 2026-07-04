import { X, Camera } from 'lucide-react'
import { Panel } from '@/components/ui/panel'
import { useMissionDraftStore } from '@/store/mission-draft-store'
import { useUiStore } from '@/store/ui-store'
import { formatCoord } from '@/utils/format'

export function WaypointDetailCard() {
  const selectedIndex = useUiStore((s) => s.selectedWaypointIndex)
  const selectWaypoint = useUiStore((s) => s.selectWaypoint)
  const mission = useMissionDraftStore((s) => s.generated?.mission_info ?? null)

  if (selectedIndex === null || !mission) return null
  const wp = mission.waypoints.find((w) => w.index === selectedIndex)
  if (!wp) return null

  return (
    <Panel className="w-64">
      <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
        <span className="text-xs font-semibold text-text-primary">Waypoint {wp.index}</span>
        <button onClick={() => selectWaypoint(null)} className="text-text-tertiary hover:text-text-primary">
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
      <div className="space-y-1.5 p-4 text-xs">
        {wp.is_capture_point && (
          <div className="flex items-center gap-1.5 text-success-500">
            <Camera className="h-3.5 w-3.5" /> Capture point
          </div>
        )}
        <Row label="Latitude" value={formatCoord(wp.latitude)} />
        <Row label="Longitude" value={formatCoord(wp.longitude)} />
        <Row label="Altitude" value={`${wp.altitude.toFixed(1)} m`} />
        {wp.param1 > 0 && <Row label="Hold time" value={`${wp.param1.toFixed(1)} s`} />}
      </div>
    </Panel>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-text-tertiary">{label}</span>
      <span className="font-mono text-text-primary">{value}</span>
    </div>
  )
}
