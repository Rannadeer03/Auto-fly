import { Trash2, X } from 'lucide-react'
import { Panel, PanelBody, PanelHeader, PanelTitle } from '@/components/ui/panel'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useMissionDraftStore } from '@/store/mission-draft-store'
import { useUiStore } from '@/store/ui-store'
import { formatCoord } from '@/utils/format'

/** Manual Mission Mode's counterpart to features/map/components/waypoint-detail-card.tsx
 * — but editable: altitude can be changed, and the item can be deleted.
 * Position is edited by dragging the marker on the map, not here. Only
 * waypoint-type items are handled here for now — a full per-type property
 * form for every item type is Phase 2C's "Mission Inspector". */
export function ManualWaypointEditCard() {
  const selectedId = useUiStore((s) => s.selectedManualItemId)
  const selectManualItem = useUiStore((s) => s.selectManualItem)
  const items = useMissionDraftStore((s) => s.manualItems)
  const updateManualItem = useMissionDraftStore((s) => s.updateManualItem)
  const removeManualItem = useMissionDraftStore((s) => s.removeManualItem)

  if (selectedId === null) return null
  const item = items.find((it) => it.id === selectedId)
  if (!item || item.type !== 'waypoint') return null

  const waypointNumber = items.filter((it) => it.type === 'waypoint').indexOf(item) + 1

  const remove = () => {
    removeManualItem(selectedId)
    selectManualItem(null)
  }

  return (
    <Panel className="w-64">
      <PanelHeader>
        <PanelTitle>Waypoint {waypointNumber}</PanelTitle>
        <button
          onClick={() => selectManualItem(null)}
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
            <div className="font-mono text-text-primary">{formatCoord(item.lat)}</div>
          </div>
          <div>
            <div className="text-text-tertiary">Longitude</div>
            <div className="font-mono text-text-primary">{formatCoord(item.lng)}</div>
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
            value={item.altitude}
            onChange={(e) =>
              updateManualItem(selectedId, { altitude: Number(e.target.value) || 0 })
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
