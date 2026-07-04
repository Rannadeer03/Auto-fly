import { useEffect, useRef, useState, type ReactNode } from 'react'
import { TerraDraw, TerraDrawPolygonMode, TerraDrawRectangleMode, TerraDrawSelectMode } from 'terra-draw'

// terra-draw defines FeatureId (string | number) in an internal module that
// isn't re-exported from the package root — mirrored here to avoid reaching
// into dist/store/store.
type FeatureId = string | number
import { TerraDrawMapLibreGLAdapter } from 'terra-draw-maplibre-gl-adapter'
import type { Polygon } from 'geojson'
import { Pentagon, RectangleHorizontal, MousePointer2, Trash2 } from 'lucide-react'
import { useMapInstance } from '@/features/map/map-context'
import { useMissionDraftStore, type LngLat } from '@/store/mission-draft-store'
import { cn } from '@/utils/cn'

type DrawTool = 'select' | 'rectangle' | 'polygon'

function ringToLngLat(polygon: Polygon): LngLat[] {
  const ring = polygon.coordinates[0]
  // GeoJSON closes the ring (first point repeated at the end) — drop it,
  // the app's own polygon math (utils/geo.ts) doesn't need the closure.
  const open = ring.length > 1 ? ring.slice(0, -1) : ring
  return open.map(([lng, lat]) => [lng, lat] as LngLat)
}

/**
 * Farm boundary drawing: rectangle or freeform polygon, single boundary at a
 * time. Finishing a shape hands its ring straight to the mission-draft store,
 * which drives survey generation (features/survey).
 */
export function FarmDrawTool() {
  const map = useMapInstance()
  const setFarmPolygon = useMissionDraftStore((s) => s.setFarmPolygon)
  const drawRef = useRef<TerraDraw | null>(null)
  const farmFeatureIdRef = useRef<FeatureId | null>(null)
  const [tool, setTool] = useState<DrawTool>('select')

  useEffect(() => {
    if (!map) return

    const draw = new TerraDraw({
      adapter: new TerraDrawMapLibreGLAdapter({ map }),
      modes: [
        new TerraDrawRectangleMode(),
        new TerraDrawPolygonMode(),
        new TerraDrawSelectMode({
          flags: {
            polygon: {
              feature: { draggable: true, coordinates: { midpoints: true, draggable: true } },
            },
            rectangle: {
              feature: { draggable: true, coordinates: { draggable: true } },
            },
          },
        }),
      ],
    })

    draw.start()
    draw.setMode('select')
    drawRef.current = draw

    const replaceFarmFeature = (id: FeatureId) => {
      const previous = farmFeatureIdRef.current
      if (previous !== null && previous !== id && draw.hasFeature(previous)) {
        draw.removeFeatures([previous])
      }
      farmFeatureIdRef.current = id
    }

    const syncFromFeature = (id: FeatureId) => {
      const feature = draw.getSnapshotFeature(id)
      if (feature && feature.geometry.type === 'Polygon') {
        setFarmPolygon(ringToLngLat(feature.geometry))
      }
    }

    draw.on('finish', (id) => {
      replaceFarmFeature(id)
      syncFromFeature(id)
      draw.setMode('select')
      setTool('select')
    })

    draw.on('change', (ids, type) => {
      if (type === 'delete' && farmFeatureIdRef.current !== null) {
        if (!draw.hasFeature(farmFeatureIdRef.current)) {
          farmFeatureIdRef.current = null
          setFarmPolygon(null)
        }
        return
      }
      if (farmFeatureIdRef.current !== null && ids.includes(farmFeatureIdRef.current)) {
        syncFromFeature(farmFeatureIdRef.current)
      }
    })

    return () => {
      draw.stop()
      drawRef.current = null
      farmFeatureIdRef.current = null
    }
  }, [map, setFarmPolygon])

  const selectTool = (next: DrawTool) => {
    drawRef.current?.setMode(next)
    setTool(next)
  }

  const clearFarm = () => {
    drawRef.current?.clear()
    farmFeatureIdRef.current = null
    setFarmPolygon(null)
    drawRef.current?.setMode('select')
    setTool('select')
  }

  return (
    <div className="glass-panel flex items-center gap-0.5 rounded-[var(--radius-control)] p-1">
      <ToolButton
        active={tool === 'rectangle'}
        onClick={() => selectTool('rectangle')}
        label="Draw rectangle farm"
        icon={<RectangleHorizontal className="h-4 w-4" />}
      />
      <ToolButton
        active={tool === 'polygon'}
        onClick={() => selectTool('polygon')}
        label="Draw polygon farm"
        icon={<Pentagon className="h-4 w-4" />}
      />
      <ToolButton
        active={tool === 'select'}
        onClick={() => selectTool('select')}
        label="Select / edit boundary"
        icon={<MousePointer2 className="h-4 w-4" />}
      />
      <div className="mx-0.5 h-5 w-px bg-border" />
      <ToolButton onClick={clearFarm} label="Clear boundary" icon={<Trash2 className="h-4 w-4" />} />
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
