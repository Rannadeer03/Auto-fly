import { useState } from 'react'
import {
  Power,
  PowerOff,
  Play,
  Pause,
  SkipForward,
  Undo2,
  ArrowDownToLine,
  OctagonX,
  Plug,
  PlugZap,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/feedback/confirm-dialog'
import { useTelemetry } from '@/hooks/use-telemetry'
import {
  useConnectDrone,
  useDisconnectDrone,
  useFlightCommand,
} from '@/features/mission-execution/hooks/use-flight-commands'

type PendingAction = 'arm' | 'disarm' | 'rtl' | 'land' | null

/** Always-visible flight command cluster — reachable from every sidebar
 * section, since RTL/Land/Emergency-Stop must never be a click away behind
 * a page switch mid-flight. */
export function CommandBar() {
  const { data: telemetry } = useTelemetry()
  const [pending, setPending] = useState<PendingAction>(null)

  const connect = useConnectDrone()
  const disconnect = useDisconnectDrone()
  const arm = useFlightCommand('arm')
  const disarm = useFlightCommand('disarm')
  const start = useFlightCommand('start')
  const pause = useFlightCommand('pause')
  const resume = useFlightCommand('resume')
  const rtl = useFlightCommand('rtl')
  const land = useFlightCommand('land')
  const emergencyStop = useFlightCommand('emergency_stop')

  const connected = telemetry?.connected ?? false
  const armed = telemetry?.armed ?? false
  const mode = telemetry?.flight_mode ?? 'UNKNOWN'
  const isLoitering = mode === 'LOITER'

  return (
    <div className="flex items-center gap-1.5">
      {connected ? (
        <Button
          size="sm"
          variant="outline"
          onClick={() => disconnect.mutate()}
          disabled={disconnect.isPending}
          title="Disconnect from Pixhawk"
        >
          <PlugZap className="h-3.5 w-3.5 text-success-500" />
          Linked
        </Button>
      ) : (
        <Button
          size="sm"
          variant="outline"
          onClick={() => connect.mutate()}
          disabled={connect.isPending}
        >
          <Plug className="h-3.5 w-3.5" />
          Connect
        </Button>
      )}

      <div className="mx-1 h-5 w-px bg-border" />

      {armed ? (
        <Button
          size="sm"
          variant="outline"
          disabled={!connected || disarm.isPending}
          onClick={() => setPending('disarm')}
        >
          <PowerOff className="h-3.5 w-3.5" />
          Disarm
        </Button>
      ) : (
        <Button
          size="sm"
          variant="outline"
          disabled={!connected || arm.isPending}
          onClick={() => setPending('arm')}
        >
          <Power className="h-3.5 w-3.5" />
          Arm
        </Button>
      )}

      {!armed || mode === 'AUTO' ? (
        <Button
          size="sm"
          variant="accent"
          disabled={!connected || !armed || start.isPending}
          onClick={() => start.mutate()}
          title="Upload the generated survey first"
        >
          <Play className="h-3.5 w-3.5" />
          Start
        </Button>
      ) : (
        <Button
          size="sm"
          variant="accent"
          disabled={!connected || resume.isPending}
          onClick={() => resume.mutate()}
        >
          <SkipForward className="h-3.5 w-3.5" />
          Resume
        </Button>
      )}

      <Button
        size="sm"
        variant="outline"
        disabled={!connected || !armed || mode !== 'AUTO' || pause.isPending}
        onClick={() => pause.mutate()}
        title={isLoitering ? 'Already loitering' : 'Pause mission (Loiter)'}
      >
        <Pause className="h-3.5 w-3.5" />
        Pause
      </Button>

      <Button
        size="sm"
        variant="outline"
        disabled={!connected || !armed || rtl.isPending}
        onClick={() => setPending('rtl')}
      >
        <Undo2 className="h-3.5 w-3.5" />
        RTL
      </Button>

      <Button
        size="sm"
        variant="outline"
        disabled={!connected || !armed || land.isPending}
        onClick={() => setPending('land')}
      >
        <ArrowDownToLine className="h-3.5 w-3.5" />
        Land
      </Button>

      <div className="mx-1 h-5 w-px bg-border" />

      <Button
        size="sm"
        variant="danger"
        disabled={!connected || emergencyStop.isPending}
        onClick={() => emergencyStop.mutate()}
        title="Force-disarm immediately — no confirmation, by design"
      >
        <OctagonX className="h-3.5 w-3.5" />
        E-Stop
      </Button>

      <ConfirmDialog
        open={pending === 'arm'}
        onOpenChange={(open) => !open && setPending(null)}
        title="Arm the drone?"
        description="This spins the motors to idle and prepares for flight. Confirm the area is clear."
        confirmLabel="Arm"
        variant="accent"
        onConfirm={() => arm.mutate()}
      />
      <ConfirmDialog
        open={pending === 'disarm'}
        onOpenChange={(open) => !open && setPending(null)}
        title="Disarm the drone?"
        description={
          armed && mode === 'AUTO'
            ? 'The drone appears to be mid-mission. Disarming now will stop the motors immediately, including in flight.'
            : 'This stops the motors.'
        }
        confirmLabel="Disarm"
        onConfirm={() => disarm.mutate()}
      />
      <ConfirmDialog
        open={pending === 'rtl'}
        onOpenChange={(open) => !open && setPending(null)}
        title="Return to Launch?"
        description="The drone will abort its current path and fly back to the home position."
        confirmLabel="Return to Launch"
        onConfirm={() => rtl.mutate()}
      />
      <ConfirmDialog
        open={pending === 'land'}
        onOpenChange={(open) => !open && setPending(null)}
        title="Land now?"
        description="The drone will begin landing at its current position."
        confirmLabel="Land"
        onConfirm={() => land.mutate()}
      />
    </div>
  )
}
