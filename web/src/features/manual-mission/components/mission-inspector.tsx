import { ArrowDownToLine, ArrowUpToLine, ChevronDown, ChevronUp, Copy, Trash2, X } from 'lucide-react'
import { Panel, PanelBody, PanelHeader, PanelTitle } from '@/components/ui/panel'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useMissionDraftStore } from '@/store/mission-draft-store'
import { useUiStore } from '@/store/ui-store'
import { hasPosition, type MissionItem, type MissionItemType } from '@/types/mission-items'
import { formatCoord } from '@/utils/format'

const TYPE_LABEL: Record<MissionItemType, string> = {
  takeoff: 'Takeoff',
  waypoint: 'Waypoint',
  loiter: 'Loiter',
  rtl: 'RTL',
  land: 'Land',
  change_speed: 'Change Speed',
}

/** Mission Inspector — clicking any mission item (on the map, or from the
 * non-positional-items chip list for RTL/Change Speed) opens this panel.
 * Replaces the Phase 2A waypoint-only edit card: every item type gets the
 * property fields relevant to it, plus the reordering actions (Duplicate/
 * Insert Before/Insert After/Move Up/Move Down/Delete) that apply
 * identically regardless of type. */
export function MissionInspector() {
  const selectedId = useUiStore((s) => s.selectedManualItemId)
  const selectManualItem = useUiStore((s) => s.selectManualItem)
  const items = useMissionDraftStore((s) => s.manualItems)
  const updateManualItem = useMissionDraftStore((s) => s.updateManualItem)
  const removeManualItem = useMissionDraftStore((s) => s.removeManualItem)
  const duplicateManualItem = useMissionDraftStore((s) => s.duplicateManualItem)
  const insertManualItemBefore = useMissionDraftStore((s) => s.insertManualItemBefore)
  const insertManualItemAfter = useMissionDraftStore((s) => s.insertManualItemAfter)
  const moveManualItemUp = useMissionDraftStore((s) => s.moveManualItemUp)
  const moveManualItemDown = useMissionDraftStore((s) => s.moveManualItemDown)

  if (selectedId === null) return null
  const index = items.findIndex((it) => it.id === selectedId)
  if (index === -1) return null
  const item = items[index]

  const sameTypeCount = items.filter((it) => it.type === item.type).length
  const sameTypeIndex = items.filter((it) => it.type === item.type).indexOf(item) + 1
  const title = sameTypeCount > 1 ? `${TYPE_LABEL[item.type]} ${sameTypeIndex}` : TYPE_LABEL[item.type]

  const remove = () => {
    removeManualItem(selectedId)
    selectManualItem(null)
  }

  return (
    <Panel className="w-72">
      <PanelHeader>
        <PanelTitle>{title}</PanelTitle>
        <button
          onClick={() => selectManualItem(null)}
          className="text-text-tertiary hover:text-text-primary"
          aria-label="Close"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </PanelHeader>
      <PanelBody className="space-y-3">
        <ItemProperties item={item} onChange={(patch) => updateManualItem(selectedId, patch)} />

        <div className="grid grid-cols-3 gap-1.5 border-t border-border pt-3">
          <Button variant="outline" size="sm" onClick={() => duplicateManualItem(selectedId)} title="Duplicate">
            <Copy className="h-3.5 w-3.5" />
            Duplicate
          </Button>
          <Button variant="outline" size="sm" onClick={() => moveManualItemUp(selectedId)} title="Move Up">
            <ChevronUp className="h-3.5 w-3.5" />
            Up
          </Button>
          <Button variant="outline" size="sm" onClick={() => moveManualItemDown(selectedId)} title="Move Down">
            <ChevronDown className="h-3.5 w-3.5" />
            Down
          </Button>
          <Button
            variant="outline" size="sm" className="col-span-1"
            onClick={() => insertManualItemBefore(selectedId)} title="Insert a new Waypoint before this item"
          >
            <ArrowUpToLine className="h-3.5 w-3.5" />
            Before
          </Button>
          <Button
            variant="outline" size="sm" className="col-span-1"
            onClick={() => insertManualItemAfter(selectedId)} title="Insert a new Waypoint after this item"
          >
            <ArrowDownToLine className="h-3.5 w-3.5" />
            After
          </Button>
          <Button variant="danger" size="sm" onClick={remove} title="Delete">
            <Trash2 className="h-3.5 w-3.5" />
            Delete
          </Button>
        </div>
      </PanelBody>
    </Panel>
  )
}

function ItemProperties({
  item,
  onChange,
}: {
  item: MissionItem
  onChange: (patch: Partial<MissionItem>) => void
}) {
  const position = hasPosition(item) ? (
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
  ) : null

  switch (item.type) {
    case 'takeoff':
    case 'waypoint':
      return (
        <>
          {position}
          <p className="text-[11px] text-text-tertiary">Drag the marker on the map to reposition.</p>
          <NumberField
            label="Altitude (m)" min={2} max={500} value={item.altitude}
            onChange={(v) => onChange({ altitude: v })}
          />
        </>
      )
    case 'loiter':
      return (
        <>
          {position}
          <p className="text-[11px] text-text-tertiary">Drag the marker on the map to reposition.</p>
          <NumberField
            label="Altitude (m)" min={2} max={500} value={item.altitude}
            onChange={(v) => onChange({ altitude: v })}
          />
          <NumberField
            label="Hold Time (s)" min={0} max={600} value={item.holdTimeS}
            onChange={(v) => onChange({ holdTimeS: v })}
          />
        </>
      )
    case 'land':
      return (
        <>
          {position}
          <p className="text-[11px] text-text-tertiary">Drag the marker on the map to reposition.</p>
        </>
      )
    case 'change_speed':
      return (
        <NumberField
          label="Speed (m/s)" min={0.5} max={25} step={0.5} value={item.speedMs}
          onChange={(v) => onChange({ speedMs: v })}
        />
      )
    case 'rtl':
      return (
        <p className="text-xs text-text-secondary">
          Returns to launch at this point in the sequence. No configurable properties — the vehicle's
          own RTL altitude/speed parameters govern the return, set under Settings on the flight
          controller.
        </p>
      )
  }
}

function NumberField({
  label, value, onChange, min, max, step = 1,
}: {
  label: string
  value: number
  onChange: (value: number) => void
  min: number
  max: number
  step?: number
}) {
  return (
    <div>
      <label className="mb-1 block text-xs text-text-tertiary">{label}</label>
      <Input
        type="number" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(Number(e.target.value) || 0)}
      />
    </div>
  )
}
