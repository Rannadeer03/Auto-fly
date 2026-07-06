import { Trash2, X } from 'lucide-react'
import { Panel, PanelBody, PanelHeader, PanelTitle } from '@/components/ui/panel'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useMissionDraftStore } from '@/store/mission-draft-store'
import { useUiStore } from '@/store/ui-store'
import { formatCoord } from '@/utils/format'

/** Manual Mission Mode's counterpart to features/map/components/waypoint-detail-card.tsx
 * — but editable: altitude can be changed, and the waypoint can be deleted.
 * Position is edited by dragging the marker on the map, not here. */
export function ManualWaypointEditCard() {
  const selectedIndex = useUiStore((s) => s.selectedWaypointIndex)
  const selectWaypoint = useUiStore((s) => s.selectWaypoint)
  const waypoints = useMissionDraftStore((s) => s.manualWaypoints)
  const updateManualWaypoint = useMissionDraftStore((s) => s.updateManualWaypoint)
  const removeManualWaypoint = useMissionDraftStore((s) => s.removeManualWaypoint)

  if (selectedIndex === null) return null
  const wp = waypoints[selectedIndex]
  if (!wp) return null

  const remove = () => {
    removeManualWaypoint(selectedIndex)
    selectWaypoint(null)
  }

  return (
    <Panel className="w-64">
      <PanelHeader>
        <PanelTitle>Waypoint {selectedIndex + 1}</PanelTitle>
        <button
          onClick={() => selectWaypoint(null)}
          className="text-text-tertiary hover:text-text-primary"
          aria-label="Close"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </PanelHeader>
      <PanelBody className="space-y-3">
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div>
            <div className="text-text-tertiary">Latitude</div>
            <div className="font-mono text-text-primary">{formatCoord(wp.lat)}</div>
          </div>
          <div>
            <div className="text-text-tertiary">Longitude</div>
            <div className="font-mono text-text-primary">{formatCoord(wp.lng)}</div>
          </div>
        </div>
        <p className="text-[11px] text-text-tertiary">Drag the marker on the map to reposition.</p>
        <div>
          <label className="mb-1 block text-xs text-text-tertiary">Altitude (m)</label>
          <Input
            type="number"
            min={2}
            max={500}
            step={1}
            value={wp.altitude}
            onChange={(e) =>
              updateManualWaypoint(selectedIndex, { altitude: Number(e.target.value) || 0 })
            }
          />
        </div>
        <Button variant="danger" size="sm" className="w-full" onClick={remove}>
          <Trash2 className="h-3.5 w-3.5" />
          Delete waypoint
        </Button>
      </PanelBody>
    </Panel>
  )
}
