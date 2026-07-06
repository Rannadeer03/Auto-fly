import { Gauge, Undo2 } from 'lucide-react'
import { useMissionDraftStore } from '@/store/mission-draft-store'
import { useUiStore } from '@/store/ui-store'
import type { ChangeSpeedItem, RtlItem } from '@/types/mission-items'
import { cn } from '@/utils/cn'

/** RTL and Change Speed items have no map position (see mission-items.ts's
 * hasPosition), so there's no marker to click to reselect/edit/delete them
 * once placed. Without a Timeline (not built until Phase 2E) they'd be
 * orphaned — placed once via the toolbox, then permanently inaccessible.
 * This is a minimal stand-in: a small ordered chip list of just the
 * non-positional items, click to open the Mission Inspector on one. Not a
 * full drag-reorder mission timeline — every positional item still lives
 * only on the map. */
export function NonPositionalItemsChips() {
  const items = useMissionDraftStore((s) => s.manualItems)
  const selectedId = useUiStore((s) => s.selectedManualItemId)
  const selectManualItem = useUiStore((s) => s.selectManualItem)

  const chips = items
    .map((item, index) => ({ item, index }))
    .filter(
      (entry): entry is { item: RtlItem | ChangeSpeedItem; index: number } =>
        entry.item.type === 'rtl' || entry.item.type === 'change_speed',
    )

  if (chips.length === 0) return null

  return (
    <div className="glass-panel flex flex-wrap items-center gap-1 rounded-[var(--radius-control)] p-1.5">
      {chips.map(({ item, index }) => {
        const label =
          item.type === 'rtl' ? 'RTL' : `Speed ${item.speedMs} m/s`
        const icon =
          item.type === 'rtl' ? <Undo2 className="h-3 w-3" /> : <Gauge className="h-3 w-3" />
        return (
          <button
            key={item.id}
            onClick={() => selectManualItem(item.id)}
            title={`Sequence position ${index + 1} — click to select`}
            className={cn(
              'flex items-center gap-1 rounded-full px-2 py-1 text-[11px] font-medium transition-colors',
              selectedId === item.id
                ? 'bg-accent-500 text-canvas'
                : 'bg-surface-3 text-text-secondary hover:text-text-primary',
            )}
          >
            {icon}
            {label}
          </button>
        )
      })}
    </div>
  )
}
