import { useState } from 'react'
import { Panel } from '@/components/ui/panel'
import { MissionLibraryList } from '@/features/mission-library/components/mission-library-list'
import { MissionLibraryDetailPanel } from '@/features/mission-library/components/mission-library-detail-panel'

export function MissionLibraryPage() {
  const [selected, setSelected] = useState<string | null>(null)

  return (
    <div className="grid h-full grid-cols-[320px_1fr] gap-4 p-4">
      <Panel className="overflow-hidden">
        <MissionLibraryList selected={selected} onSelect={setSelected} />
      </Panel>

      {selected ? (
        <MissionLibraryDetailPanel
          id={selected}
          onClose={() => setSelected(null)}
          onDeleted={() => setSelected(null)}
        />
      ) : (
        <Panel className="flex items-center justify-center">
          <p className="text-sm text-text-tertiary">Select a saved mission to view details.</p>
        </Panel>
      )}
    </div>
  )
}
