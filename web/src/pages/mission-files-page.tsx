import { useState } from 'react'
import { Panel } from '@/components/ui/panel'
import { MissionList } from '@/features/mission-history/components/mission-list'
import { MissionDetailPanel } from '@/features/mission-history/components/mission-detail-panel'

export function MissionFilesPage() {
  const [selected, setSelected] = useState<string | null>(null)

  return (
    <div className="grid h-full grid-cols-[320px_1fr] gap-4 p-4">
      <Panel className="overflow-hidden">
        <MissionList selected={selected} onSelect={setSelected} />
      </Panel>

      {selected ? (
        <MissionDetailPanel
          name={selected}
          onClose={() => setSelected(null)}
          onDeleted={() => setSelected(null)}
        />
      ) : (
        <Panel className="flex items-center justify-center">
          <p className="text-sm text-text-tertiary">Select a mission to view details.</p>
        </Panel>
      )}
    </div>
  )
}
