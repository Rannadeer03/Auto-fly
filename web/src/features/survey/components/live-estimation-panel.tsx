import { Loader2, TriangleAlert } from 'lucide-react'
import { Panel, PanelBody, PanelHeader, PanelTitle } from '@/components/ui/panel'
import { StatTile } from '@/components/ui/stat-tile'
import { Badge } from '@/components/ui/badge'
import { useMissionDraftStore } from '@/store/mission-draft-store'
import { usePlanningConfig } from '@/hooks/use-planning-config'
import { useTelemetry } from '@/hooks/use-telemetry'
import { polygonAreaM2 } from '@/utils/geo'
import { formatArea, formatDistance, formatDuration, formatPercent } from '@/utils/format'

/** The live numbers panel — recomputed every time the survey regenerates,
 * sourced from the backend's own plan_info/mission_info so the UI never
 * drifts from what will actually fly. */
export function LiveEstimationPanel() {
  const farmPolygon = useMissionDraftStore((s) => s.farmPolygon)
  const generated = useMissionDraftStore((s) => s.generated)
  const isGenerating = useMissionDraftStore((s) => s.isGenerating)
  const generateError = useMissionDraftStore((s) => s.generateError)
  const { data: planningConfig } = usePlanningConfig()
  const { data: telemetry } = useTelemetry()

  const area = farmPolygon ? polygonAreaM2(farmPolygon) : 0
  const mission = generated?.mission_info
  const planInfo = generated?.plan_info

  const gsdCmPx =
    planInfo && planningConfig
      ? (planInfo.footprint_width_m * 100) / planningConfig.camera_width_px
      : null

  const missionActive = Boolean(telemetry?.mission_uploaded && telemetry.mission.total_waypoints > 0)

  return (
    <Panel className="w-80">
      <PanelHeader>
        <PanelTitle>Live Mission Estimate</PanelTitle>
        {isGenerating && <Loader2 className="h-3.5 w-3.5 animate-spin text-accent-400" />}
      </PanelHeader>
      <PanelBody>
        {!farmPolygon ? (
          <p className="py-6 text-center text-xs text-text-tertiary">
            Draw a farm boundary on the map to generate a survey.
          </p>
        ) : generateError ? (
          <div className="flex items-start gap-2 rounded-[var(--radius-control)] bg-danger-500/10 p-3 text-xs text-danger-500">
            <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>{generateError}</span>
          </div>
        ) : (
          <div className="space-y-3">
            {missionActive && (
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-text-secondary">Mission completion</span>
                  <span className="font-mono font-semibold text-accent-400">
                    {formatPercent(telemetry!.mission.progress_percent)}
                  </span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-surface-3">
                  <div
                    className="h-full rounded-full bg-accent-500 transition-[width] duration-500"
                    style={{ width: `${telemetry!.mission.progress_percent}%` }}
                  />
                </div>
              </div>
            )}

            <div className="grid grid-cols-2 gap-2">
              <StatTile label="Farm area" value={formatArea(area)} />
              <StatTile
                label="Waypoints"
                value={mission ? String(mission.waypoint_count) : '—'}
              />
              <StatTile
                label="Flight time"
                value={mission ? formatDuration(mission.estimated_duration_minutes) : '—'}
              />
              <StatTile
                label="Battery use"
                value={mission ? formatPercent(mission.estimated_battery_percent) : '—'}
                tone={mission && mission.estimated_battery_percent > 80 ? 'warning' : 'default'}
              />
              <StatTile
                label="Photos"
                value={planInfo ? String(planInfo.estimated_photos) : '—'}
              />
              <StatTile
                label="Distance"
                value={mission ? formatDistance(mission.total_distance_m) : '—'}
              />
              <StatTile label="Altitude" value={mission ? `${mission.max_altitude_m} m` : '—'} />
              <StatTile
                label="Ground res."
                value={gsdCmPx !== null ? `${gsdCmPx.toFixed(1)} cm/px` : '—'}
              />
              <StatTile
                label="Front overlap"
                value={planInfo ? formatPercent(100 - percentFromSpacing(planInfo.photo_spacing_m, planInfo.footprint_height_m)) : '—'}
              />
              <StatTile
                label="Side overlap"
                value={planInfo ? formatPercent(100 - percentFromSpacing(planInfo.line_spacing_m, planInfo.footprint_width_m)) : '—'}
              />
            </div>

            {planInfo && (
              <div className="flex items-center gap-2 pt-1">
                <Badge variant={planInfo.capture_mode === 'hover' ? 'success' : 'info'}>
                  {planInfo.capture_mode === 'hover'
                    ? `Hover · ${planInfo.hold_time_s}s hold × ${planInfo.capture_waypoint_count}`
                    : 'Continuous capture'}
                </Badge>
                <Badge variant="neutral">{planInfo.line_count} lines</Badge>
              </div>
            )}
          </div>
        )}
      </PanelBody>
    </Panel>
  )
}

function percentFromSpacing(spacing: number, footprint: number): number {
  if (footprint <= 0) return 0
  return (spacing / footprint) * 100
}
