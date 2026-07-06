import { useRef, useState } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { Search, Route, Clock, Battery } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { useLibraryList } from '@/features/mission-library/hooks/use-mission-library'
import { formatDistance, formatDuration, formatPercent, formatTimestamp } from '@/utils/format'
import { cn } from '@/utils/cn'

interface MissionLibraryListProps {
  selected: string | null
  onSelect: (id: string) => void
}

/** Virtualized list of saved mission plans — mirrors
 * features/mission-history/components/mission-list.tsx's layout so the two
 * "library" surfaces (flight plans vs. flight records) feel consistent. */
export function MissionLibraryList({ selected, onSelect }: MissionLibraryListProps) {
  const [query, setQuery] = useState('')
  const { data, isLoading } = useLibraryList(query)
  const parentRef = useRef<HTMLDivElement>(null)

  const entries = data?.entries ?? []
  const virtualizer = useVirtualizer({
    count: entries.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 80,
    overscan: 8,
  })

  return (
    <div className="flex h-full flex-col">
      <div className="relative border-b border-border p-3">
        <Search className="absolute left-6 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-text-tertiary" />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search saved missions…"
          className="pl-8"
        />
      </div>

      <div ref={parentRef} className="flex-1 overflow-y-auto">
        {isLoading && <p className="p-4 text-xs text-text-tertiary">Loading…</p>}
        {!isLoading && entries.length === 0 && (
          <p className="p-4 text-xs text-text-tertiary">
            No saved missions yet — generate a survey and use "Save to Library".
          </p>
        )}
        <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
          {virtualizer.getVirtualItems().map((row) => {
            const entry = entries[row.index]
            return (
              <button
                key={entry.id}
                onClick={() => onSelect(entry.id)}
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  width: '100%',
                  height: row.size,
                  transform: `translateY(${row.start}px)`,
                }}
                className={cn(
                  'flex flex-col justify-center gap-1 border-b border-border px-4 text-left transition-colors',
                  selected === entry.id ? 'bg-accent-500/10' : 'hover:bg-surface-2',
                )}
              >
                <span className="truncate text-sm font-medium text-text-primary">{entry.name}</span>
                {entry.description && (
                  <span className="truncate text-[11px] text-text-tertiary">{entry.description}</span>
                )}
                <div className="flex items-center gap-3 text-[11px] text-text-tertiary">
                  <span>{formatTimestamp(entry.created_at)}</span>
                  <span className="flex items-center gap-1">
                    <Route className="h-3 w-3" /> {formatDistance(entry.total_distance_km * 1000)}
                  </span>
                  <span className="flex items-center gap-1">
                    <Clock className="h-3 w-3" /> {formatDuration(entry.estimated_duration_minutes)}
                  </span>
                  <span className="flex items-center gap-1">
                    <Battery className="h-3 w-3" /> {formatPercent(entry.estimated_battery_percent)}
                  </span>
                </div>
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}
