import type { ReactNode } from 'react'
import { Map, MousePointerClick } from 'lucide-react'
import { MissionMap } from '@/features/map/components/mission-map'
import { BaseLayerSwitcher } from '@/features/map/components/base-layer-switcher'
import { FarmDrawTool } from '@/features/map/components/farm-draw-tool'
import { DroneMarker } from '@/features/map/components/drone-marker'
import { MyLocationMarker } from '@/features/map/components/my-location-marker'
import { CenterControls } from '@/features/map/components/center-controls'
import { MissionAnchors } from '@/features/map/components/mission-anchors'
import { SurveyLayer } from '@/features/map/components/survey-layer'
import { WaypointDetailCard } from '@/features/map/components/waypoint-detail-card'
import { FlightParametersPanel } from '@/features/survey/components/flight-parameters-panel'
import { LiveEstimationPanel } from '@/features/survey/components/live-estimation-panel'
import { useAutoGenerateSurvey } from '@/features/survey/hooks/use-auto-generate-survey'
import { ManualMissionTool } from '@/features/manual-mission/components/manual-mission-tool'
import { ManualMissionLayer } from '@/features/manual-mission/components/manual-mission-layer'
import { MissionInspector } from '@/features/manual-mission/components/mission-inspector'
import { NonPositionalItemsChips } from '@/features/manual-mission/components/non-positional-items-chips'
import { MissionSettingsPanel } from '@/features/manual-mission/components/mission-settings-panel'
import { useGenerateManualMission } from '@/features/manual-mission/hooks/use-generate-manual-mission'
import { UploadMissionBar } from '@/features/mission-execution/components/upload-mission-bar'
import { useMissionDraftStore } from '@/store/mission-draft-store'
import { useUiStore, type MissionMode } from '@/store/ui-store'
import { cn } from '@/utils/cn'

/**
 * The mission-planning surface — map fills the viewport, panels float on
 * top. Mounted once by App.tsx and kept alive across sidebar navigation so
 * the MapLibre GL context (and any drawn farm boundary) never gets torn down.
 *
 * Everything here is a child of <MissionMap> — even the floating toolbar
 * chrome — because MapContext only propagates to React descendants, not DOM
 * siblings. CSS (not tree position) is what puts them where they visually sit.
 */
export function MissionPage() {
  useAutoGenerateSurvey()
  useGenerateManualMission()
  const missionMode = useUiStore((s) => s.missionMode)
  const isSurvey = missionMode === 'survey'

  return (
    <MissionMap>
      <DroneMarker />
      <MyLocationMarker />
      {isSurvey && <MissionAnchors />}
      {isSurvey ? <SurveyLayer /> : <ManualMissionLayer />}

      <div className="pointer-events-none absolute inset-0 flex flex-col justify-between p-4">
        <div className="flex flex-col gap-2">
          <div className="pointer-events-auto flex items-start justify-between">
            <div className="flex items-start gap-2">
              <MissionModeToggle />
              {isSurvey ? <FarmDrawTool /> : <ManualMissionTool />}
              <CenterControls />
            </div>
            <BaseLayerSwitcher />
          </div>

          {!isSurvey && (
            <div className="pointer-events-auto flex justify-start">
              <NonPositionalItemsChips />
            </div>
          )}
        </div>

        <div className="flex items-end justify-between gap-4">
          <div className="pointer-events-auto">
            {isSurvey ? <WaypointDetailCard /> : <MissionInspector />}
          </div>
          <div className="pointer-events-auto flex items-end gap-4">
            {isSurvey && <FlightParametersPanel />}
            <div className="flex flex-col gap-3">
              {isSurvey ? <LiveEstimationPanel /> : <MissionSettingsPanel />}
              <UploadMissionBar />
            </div>
          </div>
        </div>
      </div>
    </MissionMap>
  )
}

/** Switches between the auto-generated Survey grid and the hand-placed
 * Manual path. Switching resets the other mode's draft (farm boundary or
 * launch/home/waypoints) so there's never ambiguity about which mission is
 * "live" — mirrors setFarmPolygon's existing behavior of clearing
 * `generated` on every boundary change. */
function MissionModeToggle() {
  const missionMode = useUiStore((s) => s.missionMode)
  const setMissionMode = useUiStore((s) => s.setMissionMode)
  const reset = useMissionDraftStore((s) => s.reset)

  const select = (mode: MissionMode) => {
    if (mode === missionMode) return
    setMissionMode(mode)
    reset()
  }

  return (
    <div className="glass-panel flex items-center gap-0.5 rounded-[var(--radius-control)] p-1">
      <ModeButton
        active={missionMode === 'survey'}
        onClick={() => select('survey')}
        label="Survey"
        icon={<Map className="h-3.5 w-3.5" />}
      />
      <ModeButton
        active={missionMode === 'manual'}
        onClick={() => select('manual')}
        label="Manual"
        icon={<MousePointerClick className="h-3.5 w-3.5" />}
      />
    </div>
  )
}

function ModeButton({
  active,
  onClick,
  label,
  icon,
}: {
  active: boolean
  onClick: () => void
  label: string
  icon: ReactNode
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'flex h-8 items-center gap-1.5 rounded-[6px] px-2.5 text-xs font-medium transition-colors',
        active
          ? 'bg-accent-500 text-canvas'
          : 'text-text-secondary hover:bg-surface-3 hover:text-text-primary',
      )}
    >
      {icon}
      {label}
    </button>
  )
}
