import { useEffect, type ReactNode } from 'react'
import { useForm, type Path, type PathValue } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Compass, Wand2 } from 'lucide-react'
import { Panel, PanelBody, PanelHeader, PanelTitle } from '@/components/ui/panel'
import { LabeledSlider } from '@/components/ui/labeled-slider'
import { Input, Textarea } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { flightParamsSchema, type FlightParamsFormValues } from '@/features/survey/schema'
import { useMissionDraftStore } from '@/store/mission-draft-store'
import { longestEdgeAngleDeg } from '@/utils/geo'

export function FlightParametersPanel() {
  const flightParams = useMissionDraftStore((s) => s.flightParams)
  const updateFlightParams = useMissionDraftStore((s) => s.updateFlightParams)
  const farmPolygon = useMissionDraftStore((s) => s.farmPolygon)

  const form = useForm<FlightParamsFormValues>({
    resolver: zodResolver(flightParamsSchema),
    defaultValues: flightParams,
    mode: 'onChange',
  })

  // Push every valid change straight into the shared draft store, which the
  // debounced survey-generation hook (use-auto-generate-survey) watches.
  useEffect(() => {
    const sub = form.watch((values) => {
      if (form.formState.isValid) {
        updateFlightParams(values as FlightParamsFormValues)
      }
    })
    return () => sub.unsubscribe()
  }, [form, updateFlightParams])

  const set = <K extends Path<FlightParamsFormValues>>(
    key: K,
    value: PathValue<FlightParamsFormValues, K>,
  ) => form.setValue(key, value, { shouldValidate: true, shouldDirty: true })

  const autoAngle = farmPolygon ? Math.round(longestEdgeAngleDeg(farmPolygon)) : null

  return (
    <Panel className="w-80">
      <PanelHeader>
        <PanelTitle>Flight Parameters</PanelTitle>
      </PanelHeader>
      {/* Capped well under full viewport height (not just "whatever's left")
          so this panel — anchored to the bottom of the map overlay — can
          never grow tall enough to reach the native zoom/scale controls
          docked in the top corners (see mission-map.tsx). */}
      <PanelBody className="max-h-[55vh] space-y-5 overflow-y-auto">
        <div className="space-y-3">
          <Field label="Mission name">
            <Input
              placeholder="North Field Survey"
              {...form.register('missionName')}
            />
          </Field>
          <Field label="Description">
            <Textarea rows={2} placeholder="Optional notes" {...form.register('missionDescription')} />
          </Field>
        </div>

        <div className="h-px bg-border" />

        <LabeledSlider
          label="Altitude"
          unit=" m"
          min={2}
          max={120}
          step={1}
          value={form.watch('altitudeM')}
          onChange={(v) => set('altitudeM', v)}
        />
        <LabeledSlider
          label="Cruise speed"
          unit=" m/s"
          min={0.5}
          max={15}
          step={0.5}
          value={form.watch('speedMs')}
          onChange={(v) => set('speedMs', v)}
        />
        <LabeledSlider
          label="Front overlap"
          unit="%"
          min={0}
          max={95}
          step={5}
          value={form.watch('frontOverlapPct')}
          onChange={(v) => set('frontOverlapPct', v)}
        />
        <LabeledSlider
          label="Side overlap"
          unit="%"
          min={0}
          max={95}
          step={5}
          value={form.watch('sideOverlapPct')}
          onChange={(v) => set('sideOverlapPct', v)}
        />

        <div className="h-px bg-border" />

        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="text-text-secondary">Survey direction</span>
            <button
              type="button"
              onClick={() =>
                set(
                  'surveyDirection',
                  form.watch('surveyDirection') === 'auto' ? 'manual' : 'auto',
                )
              }
              className="flex items-center gap-1 text-[11px] font-medium text-accent-400 hover:text-accent-400/80"
            >
              {form.watch('surveyDirection') === 'auto' ? (
                <>
                  <Wand2 className="h-3 w-3" /> Auto
                </>
              ) : (
                <>
                  <Compass className="h-3 w-3" /> Manual
                </>
              )}
            </button>
          </div>
          {form.watch('surveyDirection') === 'auto' ? (
            <p className="rounded-[var(--radius-control)] bg-surface-3 px-3 py-2 text-[11px] text-text-tertiary">
              Angle computed from the farm boundary
              {autoAngle !== null ? ` — ${autoAngle}° (parallel to longest edge)` : ' once drawn'}
              , to minimize turns.
            </p>
          ) : (
            <LabeledSlider
              label="Grid angle"
              unit="°"
              min={0}
              max={179}
              step={1}
              value={form.watch('angleDeg')}
              onChange={(v) => set('angleDeg', v)}
            />
          )}
        </div>

        <div className="h-px bg-border" />

        <div className="space-y-2">
          <span className="text-xs text-text-secondary">Capture mode</span>
          <Select
            value={form.watch('captureMode')}
            onValueChange={(v) => set('captureMode', v as FlightParamsFormValues['captureMode'])}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="hover">Hover Capture (position hold + photo)</SelectItem>
              <SelectItem value="continuous">Continuous Capture (future)</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {form.watch('captureMode') === 'hover' && (
          <LabeledSlider
            label="Position hold time"
            unit=" s"
            min={0.5}
            max={5}
            step={0.5}
            value={form.watch('holdTimeS')}
            onChange={(v) => set('holdTimeS', v)}
          />
        )}

        <LabeledSlider
          label="Camera angle"
          unit="°"
          min={-90}
          max={0}
          step={5}
          value={form.watch('cameraAngleDeg')}
          onChange={(v) => set('cameraAngleDeg', v)}
        />

        <div className="flex items-center justify-between">
          <span className="text-xs text-text-secondary">Image format</span>
          <div className="flex items-center gap-2 text-xs">
            <span className={form.watch('imageFormat') === 'jpeg' ? 'text-text-primary' : 'text-text-tertiary'}>
              JPEG
            </span>
            <Switch
              checked={form.watch('imageFormat') === 'png'}
              onCheckedChange={(checked) => set('imageFormat', checked ? 'png' : 'jpeg')}
            />
            <span className={form.watch('imageFormat') === 'png' ? 'text-text-primary' : 'text-text-tertiary'}>
              PNG
            </span>
          </div>
        </div>
      </PanelBody>
    </Panel>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-xs text-text-secondary">{label}</span>
      {children}
    </label>
  )
}
