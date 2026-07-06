import type { ReactNode } from 'react'
import { Panel, PanelBody, PanelHeader, PanelTitle } from '@/components/ui/panel'
import { Input, Textarea } from '@/components/ui/input'
import { useMissionDraftStore, type FlightParams } from '@/store/mission-draft-store'

/** Manual Mission Mode's counterpart to FlightParametersPanel — global
 * mission configuration. Default Altitude/Cruise Speed/Default Hover Time
 * seed newly-placed Waypoint/Loiter items (each item's own values stay
 * independently editable afterward via the Mission Inspector); Acceptance
 * Radius is applied to every generated waypoint/loiter/land item's MAVLink
 * param2. Takeoff/Climb/Descent/RTL/Land Speed and Camera Trigger Distance
 * are stored and persisted with the mission but not yet applied to the
 * generated MAVLink item sequence — those are vehicle parameters
 * (WPNAV_SPEED_UP, RTL_SPEED, LAND_SPEED, ...) that this app doesn't push
 * to the flight controller yet, not properties of a mission item the way
 * Acceptance Radius is. Reuses the same flightParams slice of
 * mission-draft-store as Survey mode — switching modes resets it via
 * mission-draft-store's reset(), so there's no cross-mode leakage. */
export function MissionSettingsPanel() {
  const flightParams = useMissionDraftStore((s) => s.flightParams)
  const updateFlightParams = useMissionDraftStore((s) => s.updateFlightParams)

  const num = (key: keyof FlightParams) => (e: React.ChangeEvent<HTMLInputElement>) =>
    updateFlightParams({ [key]: Number(e.target.value) || 0 } as Partial<FlightParams>)

  return (
    <Panel className="w-80">
      <PanelHeader>
        <PanelTitle>Mission Settings</PanelTitle>
      </PanelHeader>
      <PanelBody className="max-h-[55vh] space-y-3 overflow-y-auto">
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
            <Input type="number" min={2} max={500} value={flightParams.altitudeM} onChange={num('altitudeM')} />
          </Field>
          <Field label="Cruise speed (m/s)">
            <Input type="number" min={0.5} max={25} step={0.5} value={flightParams.speedMs} onChange={num('speedMs')} />
          </Field>
          <Field label="Takeoff speed (m/s)">
            <Input type="number" min={0.5} max={10} step={0.5} value={flightParams.takeoffSpeedMs} onChange={num('takeoffSpeedMs')} />
          </Field>
          <Field label="Climb speed (m/s)">
            <Input type="number" min={0.5} max={10} step={0.5} value={flightParams.climbSpeedMs} onChange={num('climbSpeedMs')} />
          </Field>
          <Field label="Descent speed (m/s)">
            <Input type="number" min={0.5} max={10} step={0.5} value={flightParams.descentSpeedMs} onChange={num('descentSpeedMs')} />
          </Field>
          <Field label="RTL speed (m/s)">
            <Input type="number" min={0.5} max={25} step={0.5} value={flightParams.rtlSpeedMs} onChange={num('rtlSpeedMs')} />
          </Field>
          <Field label="Land speed (m/s)">
            <Input type="number" min={0.1} max={5} step={0.1} value={flightParams.landSpeedMs} onChange={num('landSpeedMs')} />
          </Field>
          <Field label="Default hover time (s)">
            <Input type="number" min={0} max={600} value={flightParams.holdTimeS} onChange={num('holdTimeS')} />
          </Field>
          <Field label="Acceptance radius (m)">
            <Input type="number" min={0.5} max={50} step={0.5} value={flightParams.acceptanceRadiusM} onChange={num('acceptanceRadiusM')} />
          </Field>
          <Field label="Camera trigger dist. (m)">
            <Input type="number" min={1} max={200} value={flightParams.cameraTriggerDistanceM} onChange={num('cameraTriggerDistanceM')} />
          </Field>
        </div>

        <p className="text-[11px] text-text-tertiary">
          Default Altitude, Cruise Speed, Default Hover Time and Acceptance Radius apply to newly
          placed items and the generated mission. Takeoff/Climb/Descent/RTL/Land Speed and Camera
          Trigger Distance are saved with the mission but not yet sent to the vehicle.
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
