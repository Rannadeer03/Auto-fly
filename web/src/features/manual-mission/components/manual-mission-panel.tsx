import type { ReactNode } from 'react'
import { Panel, PanelBody, PanelHeader, PanelTitle } from '@/components/ui/panel'
import { Input, Textarea } from '@/components/ui/input'
import { useMissionDraftStore } from '@/store/mission-draft-store'

/** Manual Mission Mode's counterpart to FlightParametersPanel — mission
 * name/description plus the default altitude/speed newly-placed waypoints
 * pick up (each waypoint's own altitude stays independently editable
 * afterward via ManualWaypointEditCard). Reuses the same flightParams slice
 * of mission-draft-store as Survey mode — switching modes resets it via
 * mission-draft-store's reset(), so there's no cross-mode leakage. */
export function ManualMissionPanel() {
  const flightParams = useMissionDraftStore((s) => s.flightParams)
  const updateFlightParams = useMissionDraftStore((s) => s.updateFlightParams)

  return (
    <Panel className="w-80">
      <PanelHeader>
        <PanelTitle>Manual Mission</PanelTitle>
      </PanelHeader>
      <PanelBody className="space-y-3">
        <Field label="Mission name">
          <Input
            placeholder="Field Inspection Run"
            value={flightParams.missionName}
            onChange={(e) => updateFlightParams({ missionName: e.target.value })}
          />
        </Field>
        <Field label="Description">
          <Textarea
            rows={2}
            placeholder="Optional notes"
            value={flightParams.missionDescription}
            onChange={(e) => updateFlightParams({ missionDescription: e.target.value })}
          />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Default altitude (m)">
            <Input
              type="number"
              min={2}
              max={500}
              value={flightParams.altitudeM}
              onChange={(e) => updateFlightParams({ altitudeM: Number(e.target.value) || 0 })}
            />
          </Field>
          <Field label="Speed (m/s)">
            <Input
              type="number"
              min={0.5}
              max={25}
              step={0.5}
              value={flightParams.speedMs}
              onChange={(e) => updateFlightParams({ speedMs: Number(e.target.value) || 0 })}
            />
          </Field>
        </div>
        <p className="text-[11px] text-text-tertiary">
          New waypoints use the default altitude above — edit any waypoint's altitude individually
          by clicking it on the map.
        </p>
      </PanelBody>
    </Panel>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <label className="mb-1 block text-xs text-text-tertiary">{label}</label>
      {children}
    </div>
  )
}
