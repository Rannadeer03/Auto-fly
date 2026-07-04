import { MissionMap } from '@/features/map/components/mission-map'
import { BaseLayerSwitcher } from '@/features/map/components/base-layer-switcher'
import { FarmDrawTool } from '@/features/map/components/farm-draw-tool'
import { DroneMarker } from '@/features/map/components/drone-marker'
import { MissionAnchors } from '@/features/map/components/mission-anchors'
import { SurveyLayer } from '@/features/map/components/survey-layer'
import { WaypointDetailCard } from '@/features/map/components/waypoint-detail-card'
import { FlightParametersPanel } from '@/features/survey/components/flight-parameters-panel'
import { LiveEstimationPanel } from '@/features/survey/components/live-estimation-panel'
import { useAutoGenerateSurvey } from '@/features/survey/hooks/use-auto-generate-survey'
import { UploadMissionBar } from '@/features/mission-execution/components/upload-mission-bar'

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

  return (
    <MissionMap>
      <DroneMarker />
      <MissionAnchors />
      <SurveyLayer />

      <div className="pointer-events-none absolute inset-0 flex flex-col justify-between p-4">
        <div className="pointer-events-auto flex items-start justify-between">
          <FarmDrawTool />
          <BaseLayerSwitcher />
        </div>

        <div className="flex items-end justify-between gap-4">
          <div className="pointer-events-auto">
            <WaypointDetailCard />
          </div>
          <div className="pointer-events-auto flex items-end gap-4">
            <FlightParametersPanel />
            <div className="flex flex-col gap-3">
              <LiveEstimationPanel />
              <UploadMissionBar />
            </div>
          </div>
        </div>
      </div>
    </MissionMap>
  )
}
