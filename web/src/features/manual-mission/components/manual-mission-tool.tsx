import { useEffect, useRef, useState, type ReactNode } from 'react'
import { PlaneTakeoff, Home, MapPin, Repeat, Undo2, PlaneLanding, Gauge, Trash2 } from 'lucide-react'
import { useMapInstance } from '@/features/map/map-context'
import { useMissionDraftStore } from '@/store/mission-draft-store'
import { useUiStore } from '@/store/ui-store'
import { isClickSuppressed } from '@/features/manual-mission/drag-suppression'
import { cn } from '@/utils/cn'

// The four positional tools wait for a map click before placing anything;
// 'rtl' and 'change_speed' have no map location (see mission-items.ts's
// hasPosition) so their buttons place the item immediately on click — the
// toolbar never actually enters those two as a "waiting for map click" mode.
type ManualTool = 'select' | 'home' | 'takeoff' | 'waypoint' | 'loiter' | 'land'

// A click landing on an existing marker must still place a new point when a
// placement tool is active — MapLibre markers sit as DOM siblings of the
// canvas inside its container, so a click there never reaches the canvas
// and MapLibre's own synthetic `map.on('click', ...)` event never fires
// (confirmed empirically: the marker swallows it, which is why "sometimes
// clicking does not create markers" — it was every time a click landed
// on/near an existing marker). Listening on the shared canvas container in
// the capture phase — before any marker's own bubble-phase listener runs —
// and computing the position with `map.unproject()` sidesteps that
// entirely; it's a plain native DOM event, not MapLibre's own click.
const CLICK_MOVE_THRESHOLD_PX = 4

/**
 * Mission Toolbox for Manual Mission Mode — the point-to-point counterpart
 * to features/map/components/farm-draw-tool.tsx. Takeoff/Home are one-shot
 * (placing one returns to `select` immediately); Waypoint/Loiter/Land stay
 * active for repeated clicks until the user switches tool. RTL and Change
 * Speed have no map position, so their buttons append the item immediately
 * and select it — there is no "waiting for a click" state for them.
 */
export function ManualMissionTool() {
  const map = useMapInstance()
  const [tool, setTool] = useState<ManualTool>('select')
  const toolRef = useRef(tool)
  toolRef.current = tool

  const setManualHome = useMissionDraftStore((s) => s.setManualHome)
  const addManualItem = useMissionDraftStore((s) => s.addManualItem)
  const clearManualMission = useMissionDraftStore((s) => s.clearManualMission)
  const selectManualItem = useUiStore((s) => s.selectManualItem)

  useEffect(() => {
    if (!map) return
    const container = map.getCanvasContainer()
    let downPos: { x: number; y: number } | null = null

    const onPointerDown = (e: PointerEvent) => {
      downPos = { x: e.clientX, y: e.clientY }
    }

    const onClick = (e: MouseEvent) => {
      const start = downPos
      downPos = null
      if (toolRef.current === 'select') return
      if (isClickSuppressed()) return // tail end of a marker drag, not a placement click
      // Tail end of a map-pan drag (mousedown far from mouseup) — a native
      // listener has no built-in drag-vs-click disambiguation the way
      // MapLibre's own synthetic click does, so do it manually.
      if (start && Math.hypot(e.clientX - start.x, e.clientY - start.y) > CLICK_MOVE_THRESHOLD_PX) return

      const rect = container.getBoundingClientRect()
      const { lng, lat } = map.unproject([e.clientX - rect.left, e.clientY - rect.top])
      switch (toolRef.current) {
        case 'home':
          setManualHome([lng, lat])
          setTool('select')
          break
        case 'takeoff':
          addManualItem('takeoff', [lng, lat])
          setTool('select')
          break
        case 'waypoint':
          addManualItem('waypoint', [lng, lat])
          break
        case 'loiter':
          addManualItem('loiter', [lng, lat])
          break
        case 'land':
          addManualItem('land', [lng, lat])
          break
        default:
          break
      }
    }

    // Capture phase: runs before a marker's own (bubble-phase) click
    // listener, and — unlike MapLibre's synthetic click — fires even when
    // the click target is a marker `<div>` rather than the canvas.
    container.addEventListener('pointerdown', onPointerDown, true)
    container.addEventListener('click', onClick, true)
    return () => {
      container.removeEventListener('pointerdown', onPointerDown, true)
      container.removeEventListener('click', onClick, true)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map])

  useEffect(() => {
    if (!map) return
    map.getCanvas().style.cursor = tool === 'select' ? '' : 'crosshair'
    return () => {
      if (map.getCanvas()) map.getCanvas().style.cursor = ''
    }
  }, [map, tool])

  const clear = () => {
    clearManualMission()
    setTool('select')
  }

  const toggle = (t: ManualTool) => setTool((cur) => (cur === t ? 'select' : t))

  // No map position — append immediately and open the Inspector on it,
  // since there's no marker to click afterward (no Timeline yet either).
  const appendInstantly = (type: 'rtl' | 'change_speed') => {
    const id = addManualItem(type)
    selectManualItem(id)
    setTool('select')
  }

  return (
    <div className="glass-panel flex items-center gap-0.5 rounded-[var(--radius-control)] p-1">
      <ToolButton
        active={tool === 'home'}
        onClick={() => toggle('home')}
        label="Place Home marker"
        icon={<Home className="h-4 w-4" />}
      />
      <div className="mx-0.5 h-5 w-px bg-border" />
      <ToolButton
        active={tool === 'takeoff'}
        onClick={() => toggle('takeoff')}
        label="Place Takeoff"
        icon={<PlaneTakeoff className="h-4 w-4" />}
      />
      <ToolButton
        active={tool === 'waypoint'}
        onClick={() => toggle('waypoint')}
        label="Add Waypoints (click the map repeatedly)"
        icon={<MapPin className="h-4 w-4" />}
      />
      <ToolButton
        active={tool === 'loiter'}
        onClick={() => toggle('loiter')}
        label="Add Loiter"
        icon={<Repeat className="h-4 w-4" />}
      />
      <ToolButton
        active={tool === 'land'}
        onClick={() => toggle('land')}
        label="Add Land"
        icon={<PlaneLanding className="h-4 w-4" />}
      />
      <ToolButton
        onClick={() => appendInstantly('change_speed')}
        label="Add Change Speed"
        icon={<Gauge className="h-4 w-4" />}
      />
      <ToolButton
        onClick={() => appendInstantly('rtl')}
        label="Add RTL (Return to Launch)"
        icon={<Undo2 className="h-4 w-4" />}
      />
      <div className="mx-0.5 h-5 w-px bg-border" />
      <ToolButton onClick={clear} label="Clear manual mission" icon={<Trash2 className="h-4 w-4" />} />
    </div>
  )
}

function ToolButton({
  active,
  onClick,
  label,
  icon,
}: {
  active?: boolean
  onClick: () => void
  label: string
  icon: ReactNode
}) {
  return (
    <button
      onClick={onClick}
      title={label}
      aria-label={label}
      className={cn(
        'flex h-8 w-8 items-center justify-center rounded-[6px] transition-colors',
        active
          ? 'bg-accent-500 text-canvas'
          : 'text-text-secondary hover:bg-surface-3 hover:text-text-primary',
      )}
    >
      {icon}
    </button>
  )
}
