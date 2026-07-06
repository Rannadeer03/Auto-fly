import { useEffect, useRef, useState, type ReactNode } from 'react'
import type maplibregl from 'maplibre-gl'
import { Rocket, Home, MapPin, Trash2 } from 'lucide-react'
import { useMapInstance } from '@/features/map/map-context'
import { useMissionDraftStore } from '@/store/mission-draft-store'
import { cn } from '@/utils/cn'

type ManualTool = 'select' | 'launch' | 'home' | 'waypoint'

/**
 * Launch / Home / Waypoint placement toolbar for Manual Mission Mode —
 * the point-to-point counterpart to features/map/components/farm-draw-tool.tsx.
 *
 * Unlike terra-draw's shape-drawing modes, this uses a single raw
 * `map.on('click', ...)` listener (heterogeneous marker types with
 * per-marker drag support don't fit terra-draw's point/line/polygon model).
 * Launch/Home are one-shot — placing one returns to `select` immediately.
 * Waypoint stays active for repeated clicks until the user switches tool,
 * since a manual path is normally built from several clicks in a row.
 */
export function ManualMissionTool() {
  const map = useMapInstance()
  const [tool, setTool] = useState<ManualTool>('select')
  const toolRef = useRef(tool)
  toolRef.current = tool

  const setManualLaunch = useMissionDraftStore((s) => s.setManualLaunch)
  const setManualHome = useMissionDraftStore((s) => s.setManualHome)
  const addManualWaypoint = useMissionDraftStore((s) => s.addManualWaypoint)
  const clearManualMission = useMissionDraftStore((s) => s.clearManualMission)
  const defaultAltitude = useMissionDraftStore((s) => s.flightParams.altitudeM)
  const defaultAltitudeRef = useRef(defaultAltitude)
  defaultAltitudeRef.current = defaultAltitude

  useEffect(() => {
    if (!map) return

    const onClick = (e: maplibregl.MapMouseEvent) => {
      const { lng, lat } = e.lngLat
      switch (toolRef.current) {
        case 'launch':
          setManualLaunch([lng, lat])
          setTool('select')
          break
        case 'home':
          setManualHome([lng, lat])
          setTool('select')
          break
        case 'waypoint':
          addManualWaypoint({ lat, lng, altitude: defaultAltitudeRef.current })
          break
        default:
          break
      }
    }

    map.on('click', onClick)
    return () => {
      map.off('click', onClick)
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

  return (
    <div className="glass-panel flex items-center gap-0.5 rounded-[var(--radius-control)] p-1">
      <ToolButton
        active={tool === 'launch'}
        onClick={() => setTool(tool === 'launch' ? 'select' : 'launch')}
        label="Place Launch marker"
        icon={<Rocket className="h-4 w-4" />}
      />
      <ToolButton
        active={tool === 'home'}
        onClick={() => setTool(tool === 'home' ? 'select' : 'home')}
        label="Place Home marker"
        icon={<Home className="h-4 w-4" />}
      />
      <ToolButton
        active={tool === 'waypoint'}
        onClick={() => setTool(tool === 'waypoint' ? 'select' : 'waypoint')}
        label="Add waypoints (click the map repeatedly)"
        icon={<MapPin className="h-4 w-4" />}
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
