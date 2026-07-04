import { useQuery } from '@tanstack/react-query'
import { Cable, Radio } from 'lucide-react'
import { Panel, PanelBody, PanelHeader, PanelTitle } from '@/components/ui/panel'
import { StatTile } from '@/components/ui/stat-tile'
import { Badge } from '@/components/ui/badge'
import { HealthGrid } from '@/features/telemetry/components/health-grid'
import { useHealth } from '@/hooks/use-health'
import { useTelemetry } from '@/hooks/use-telemetry'
import { useMissionSession } from '@/hooks/use-mission-session'
import { fetchPorts } from '@/services/connection-service'
import { formatTimestamp } from '@/utils/format'

export function DroneStatusPage() {
  const { data: health } = useHealth()
  const { data: telemetry } = useTelemetry()
  const { data: session } = useMissionSession()
  const { data: ports } = useQuery({ queryKey: ['ports'], queryFn: fetchPorts, staleTime: 10_000 })

  return (
    <div className="mx-auto max-w-4xl space-y-4 p-6">
      <Panel>
        <PanelHeader>
          <PanelTitle>Link</PanelTitle>
          <Badge variant={health?.drone_connected ? 'success' : 'danger'} dot>
            {health?.drone_connected ? 'Connected' : 'Disconnected'}
          </Badge>
        </PanelHeader>
        <PanelBody className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <StatTile label="Version" value={health?.version ?? '—'} />
          <StatTile label="MAVLink port" value={health?.mavlink_port ?? '—'} />
          <StatTile
            label="Heartbeat"
            value={telemetry ? `${telemetry.last_heartbeat_ago_s.toFixed(1)}s ago` : '—'}
            tone={telemetry && telemetry.last_heartbeat_ago_s > 3 ? 'warning' : 'default'}
          />
          <StatTile
            label="Link quality"
            value={telemetry ? `${telemetry.link_quality_percent.toFixed(0)}%` : '—'}
          />
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader>
          <PanelTitle>Available Serial Ports</PanelTitle>
        </PanelHeader>
        <PanelBody>
          {ports?.ports.length ? (
            <ul className="space-y-1.5">
              {ports.ports.map((p) => (
                <li key={p} className="flex items-center gap-2 text-xs text-text-secondary">
                  <Cable className="h-3.5 w-3.5 text-text-tertiary" />
                  <span className="font-mono">{p}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-text-tertiary">
              {ports?.error ?? 'No candidate ports detected — MAVLINK_PORT is set to "auto".'}
            </p>
          )}
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader>
          <PanelTitle>Mission Automation Session</PanelTitle>
          {session?.active && (
            <Badge variant="danger" dot>
              <Radio className="h-3 w-3" /> Recording
            </Badge>
          )}
        </PanelHeader>
        <PanelBody className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <StatTile label="Capture mode" value={session?.capture_mode ?? '—'} />
          <StatTile label="Photos captured" value={String(session?.photos_captured ?? 0)} />
          <StatTile label="Started" value={formatTimestamp(session?.started_at)} />
          <StatTile label="Last completed" value={session?.last_completed ?? '—'} />
        </PanelBody>
      </Panel>

      {telemetry && (
        <Panel>
          <PanelHeader>
            <PanelTitle>Sensor Health</PanelTitle>
          </PanelHeader>
          <PanelBody>
            <HealthGrid health={telemetry.health} />
          </PanelBody>
        </Panel>
      )}
    </div>
  )
}
