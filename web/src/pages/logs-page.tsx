import { useEffect, useRef, useState } from 'react'
import { Trash2, Pause, Play } from 'lucide-react'
import { Panel, PanelBody, PanelHeader, PanelTitle } from '@/components/ui/panel'
import { Button } from '@/components/ui/button'
import { useClearLogs, useLogs } from '@/features/logs/hooks/use-logs'
import type { LogEntry } from '@/types/system'
import { cn } from '@/utils/cn'

function levelTone(level: string): string {
  if (level === 'ERROR' || level === 'CRITICAL') return 'text-danger-500'
  if (level === 'WARNING') return 'text-warning-500'
  return 'text-text-secondary'
}

function formatEntry(entry: LogEntry): string {
  return `${entry.ts} [${entry.level}] ${entry.logger} — ${entry.msg}`
}

export function LogsPage() {
  const [live, setLive] = useState(true)
  const { data } = useLogs(live)
  const clear = useClearLogs()
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (live) bottomRef.current?.scrollIntoView({ block: 'end' })
  }, [data, live])

  return (
    <div className="mx-auto h-full max-w-4xl p-6">
      <Panel className="flex h-full flex-col">
        <PanelHeader>
          <PanelTitle>Application Logs</PanelTitle>
          <div className="flex items-center gap-1.5">
            <Button size="sm" variant="ghost" onClick={() => setLive((v) => !v)}>
              {live ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
              {live ? 'Live' : 'Paused'}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => clear.mutate()}>
              <Trash2 className="h-3.5 w-3.5" />
              Clear
            </Button>
          </div>
        </PanelHeader>
        <PanelBody className="flex-1 overflow-y-auto font-mono text-[11px] leading-relaxed">
          {(data?.logs ?? []).map((entry, i) => (
            <div key={i} className={cn('whitespace-pre-wrap', levelTone(entry.level))}>
              {formatEntry(entry)}
            </div>
          ))}
          <div ref={bottomRef} />
        </PanelBody>
      </Panel>
    </div>
  )
}
