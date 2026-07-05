import { Panel, PanelBody, PanelHeader, PanelTitle } from '@/components/ui/panel'
import { StatTile } from '@/components/ui/stat-tile'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { usePlanningConfig } from '@/hooks/use-planning-config'
import { useUiStore } from '@/store/ui-store'
import { BASE_LAYER_LABELS } from '@/constants/map'
import type { BaseLayerId } from '@/constants/map'

export function SettingsPage() {
  const { data: config, isLoading } = usePlanningConfig()
  const baseLayer = useUiStore((s) => s.baseLayer)
  const setBaseLayer = useUiStore((s) => s.setBaseLayer)

  return (
    <div className="mx-auto max-w-3xl space-y-4 p-6">
      <Panel>
        <PanelHeader>
          <PanelTitle>App Preferences</PanelTitle>
        </PanelHeader>
        <PanelBody className="space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-secondary">Default map base layer</span>
            <Select value={baseLayer} onValueChange={(v) => setBaseLayer(v as BaseLayerId)}>
              <SelectTrigger className="w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(Object.keys(BASE_LAYER_LABELS) as BaseLayerId[]).map((id) => (
                  <SelectItem key={id} value={id}>
                    {BASE_LAYER_LABELS[id]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader>
          <PanelTitle>Server Planning Defaults</PanelTitle>
        </PanelHeader>
        <PanelBody>
          {isLoading || !config ? (
            <p className="text-xs text-text-tertiary">Loading…</p>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                <StatTile label="Altitude" value={`${config.altitude_m} m`} />
                <StatTile label="Speed" value={`${config.speed_ms} m/s`} />
                <StatTile label="Front overlap" value={`${config.front_overlap_pct}%`} />
                <StatTile label="Side overlap" value={`${config.side_overlap_pct}%`} />
                <StatTile label="Grid angle" value={`${config.grid_angle_deg}°`} />
                <StatTile label="Capture mode" value={config.capture_mode} />
                <StatTile label="Hover hold time" value={`${config.hover_hold_time_s} s`} />
                <StatTile label="Camera HFOV" value={`${config.camera_hfov_deg}°`} />
                <StatTile label="Camera VFOV" value={`${config.camera_vfov_deg}°`} />
                <StatTile
                  label="Camera resolution"
                  value={`${config.camera_width_px}×${config.camera_height_px}`}
                />
                <StatTile label="Recording" value={config.recording_enabled ? 'Enabled' : 'Disabled'} />
              </div>
              <p className="mt-4 text-[11px] text-text-tertiary">
                These come from the drone computer's server/.env — change them there and restart
                the service to apply new defaults across missions.
              </p>
            </>
          )}
        </PanelBody>
      </Panel>
    </div>
  )
}
