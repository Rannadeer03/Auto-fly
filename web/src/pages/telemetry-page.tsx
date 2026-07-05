import { WifiOff } from 'lucide-react'
import { Panel, PanelBody, PanelHeader, PanelTitle } from '@/components/ui/panel'
import { StatTile } from '@/components/ui/stat-tile'
import { Badge } from '@/components/ui/badge'
import { AttitudeIndicator } from '@/features/telemetry/components/attitude-indicator'
import { HealthGrid } from '@/features/telemetry/components/health-grid'
import { useTelemetry } from '@/hooks/use-telemetry'
import { FLIGHT_MODE_LABELS } from '@/constants/mavlink'
import { formatDistance, formatPercent } from '@/utils/format'

export function TelemetryPage() {
  const { data: t, isError } = useTelemetry()

  if (!t || isError) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-text-tertiary">
        <WifiOff className="h-8 w-8" />
        <p className="text-sm">No telemetry available.</p>
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="mx-auto grid max-w-6xl grid-cols-1 gap-4 lg:grid-cols-3">
        <Panel className="lg:col-span-1">
          <PanelHeader>
            <PanelTitle>Attitude</PanelTitle>
            <Badge variant="accent">{FLIGHT_MODE_LABELS[t.flight_mode] ?? t.flight_mode}</Badge>
          </PanelHeader>
          <PanelBody className="flex flex-col items-center gap-4">
            <AttitudeIndicator rollDeg={t.attitude.roll_deg} pitchDeg={t.attitude.pitch_deg} />
            <div className="grid w-full grid-cols-3 gap-2 text-center text-xs">
              <div>
                <div className="text-text-tertiary">Roll</div>
                <div className="font-mono text-text-primary">{t.attitude.roll_deg.toFixed(1)}°</div>
              </div>
              <div>
                <div className="text-text-tertiary">Pitch</div>
                <div className="font-mono text-text-primary">{t.attitude.pitch_deg.toFixed(1)}°</div>
              </div>
              <div>
                <div className="text-text-tertiary">Yaw</div>
                <div className="font-mono text-text-primary">{t.attitude.yaw_deg.toFixed(1)}°</div>
              </div>
            </div>
          </PanelBody>
        </Panel>

        <Panel className="lg:col-span-2">
          <PanelHeader>
            <PanelTitle>Position &amp; Speed</PanelTitle>
          </PanelHeader>
          <PanelBody className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <StatTile label="Ground speed" value={`${t.position.ground_speed.toFixed(1)} m/s`} />
            <StatTile label="Air speed" value={`${t.position.air_speed.toFixed(1)} m/s`} />
            <StatTile label="Heading" value={`${t.position.heading}°`} />
            <StatTile label="Climb rate" value={`${t.position.climb_rate.toFixed(1)} m/s`} />
            <StatTile label="Altitude (rel)" value={`${t.position.altitude_rel.toFixed(1)} m`} />
            <StatTile label="Altitude (MSL)" value={`${t.position.altitude_msl.toFixed(1)} m`} />
            <StatTile label="Latitude" value={t.position.latitude.toFixed(6)} />
            <StatTile label="Longitude" value={t.position.longitude.toFixed(6)} />
          </PanelBody>
        </Panel>

        <Panel>
          <PanelHeader>
            <PanelTitle>GPS</PanelTitle>
          </PanelHeader>
          <PanelBody className="grid grid-cols-2 gap-2">
            <StatTile label="Satellites" value={String(t.gps.satellites_visible)} />
            <StatTile label="Fix" value={t.gps.fix_type_str} />
            <StatTile label="HDOP" value={t.gps.hdop.toFixed(2)} />
            <StatTile label="VDOP" value={t.gps.vdop.toFixed(2)} />
          </PanelBody>
        </Panel>

        <Panel>
          <PanelHeader>
            <PanelTitle>Battery</PanelTitle>
          </PanelHeader>
          <PanelBody className="grid grid-cols-2 gap-2">
            <StatTile
              label="Remaining"
              value={t.battery.remaining_percent >= 0 ? formatPercent(t.battery.remaining_percent) : '—'}
              tone={t.battery.remaining_percent >= 0 && t.battery.remaining_percent < 20 ? 'warning' : 'default'}
            />
            <StatTile label="Voltage" value={`${t.battery.voltage.toFixed(1)} V`} />
            <StatTile label="Current" value={`${t.battery.current.toFixed(1)} A`} />
            <StatTile label="Consumed" value={`${t.battery.consumed_mah.toFixed(0)} mAh`} />
          </PanelBody>
        </Panel>

        <Panel>
          <PanelHeader>
            <PanelTitle>Mission Progress</PanelTitle>
          </PanelHeader>
          <PanelBody className="grid grid-cols-2 gap-2">
            <StatTile
              label="Waypoint"
              value={`${t.mission.current_waypoint} / ${t.mission.total_waypoints}`}
            />
            <StatTile label="Progress" value={formatPercent(t.mission.progress_percent)} />
            <StatTile
              label="Dist. to WP"
              value={formatDistance(t.mission.distance_to_waypoint_m)}
              className="col-span-2"
            />
          </PanelBody>
        </Panel>

        <Panel className="lg:col-span-3">
          <PanelHeader>
            <PanelTitle>System Health</PanelTitle>
            <Badge variant={t.connected ? 'success' : 'danger'} dot>
              {t.connected ? `Link ${formatPercent(t.link_quality_percent)}` : 'No link'}
            </Badge>
          </PanelHeader>
          <PanelBody>
            <HealthGrid health={t.health} />
          </PanelBody>
        </Panel>
      </div>
    </div>
  )
}
