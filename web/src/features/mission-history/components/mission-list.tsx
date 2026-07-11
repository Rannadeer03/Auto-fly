import { useRef, useState } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { Search, Video, Camera, HardDrive, Radio } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { useMissionList } from '@/features/mission-history/hooks/use-missions'
import { formatBytes, formatTimestamp } from '@/utils/format'
import { cn } from '@/utils/cn'

interface MissionListProps {
  selected: string | null
  onSelect: (name: string) => void
}

/** Virtualized so the list stays smooth even with hundreds of recorded
 * mission folders — only the visible rows are ever mounted. */
export function MissionList({ selected, onSelect }: MissionListProps) {
  const [query, setQuery] = useState('')
  const { data, isLoading, isError, error } = useMissionList(query)
  const parentRef = useRef<HTMLDivElement>(null)

  const missions = data?.missions ?? []
  const virtualizer = useVirtualizer({
    count: missions.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 76,
    overscan: 8,
  })

  return (
    <div className="flex h-full flex-col">
      <div className="relative border-b border-border p-3">
        <Search className="absolute left-6 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-text-tertiary" />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search missions…"
          className="pl-8"
        />
      </div>

      <div ref={parentRef} className="flex-1 overflow-y-auto">
        {isLoading && <p className="p-4 text-xs text-text-tertiary">Loading…</p>}
        {isError && (
          <p className="p-4 text-xs text-danger-500">
            Could not load missions — {error instanceof Error ? error.message : 'unknown error'}
          </p>
        )}
        {!isLoading && !isError && missions.length === 0 && (
          <p className="p-4 text-xs text-text-tertiary">No missions recorded yet.</p>
        )}
        <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
          {virtualizer.getVirtualItems().map((row) => {
            const mission = missions[row.index]
            return (
              <button
                key={mission.name}
                onClick={() => onSelect(mission.name)}
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
                  selected === mission.name ? 'bg-accent-500/10' : 'hover:bg-surface-2',
                )}
              >
                <div className="flex items-center justify-between">
                  <span className="truncate text-sm font-medium text-text-primary">
                    {mission.metadata?.mission_name || mission.name}
                  </span>
                  {mission.active && (
                    <Badge variant="danger" dot>
                      <Radio className="h-3 w-3" /> Live
                    </Badge>
                  )}
                </div>
                <div className="flex items-center gap-3 text-[11px] text-text-tertiary">
                  <span>{formatTimestamp(mission.metadata?.started_at)}</span>
                  <span className="flex items-center gap-1">
                    <Camera className="h-3 w-3" /> {mission.photo_count}
                  </span>
                  {mission.has_video && (
                    <span className="flex items-center gap-1">
                      <Video className="h-3 w-3" />
                    </span>
                  )}
                  <span className="flex items-center gap-1">
                    <HardDrive className="h-3 w-3" /> {formatBytes(mission.total_size_bytes)}
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
