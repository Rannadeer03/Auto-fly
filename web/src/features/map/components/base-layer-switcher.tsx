import { useEffect } from 'react'
import { Layers } from 'lucide-react'
import { useMapInstance } from '@/features/map/map-context'
import { useUiStore } from '@/store/ui-store'
import { ALL_BASE_LAYER_IDS, BASE_LAYER_LABELS, BASE_LAYER_VISIBLE_LAYERS } from '@/constants/map'
import type { BaseLayerId } from '@/constants/map'
import { cn } from '@/utils/cn'

const LAYER_ORDER: BaseLayerId[] = ['satellite', 'hybrid', 'street']

export function BaseLayerSwitcher() {
  const map = useMapInstance()
  const baseLayer = useUiStore((s) => s.baseLayer)
  const setBaseLayer = useUiStore((s) => s.setBaseLayer)

  useEffect(() => {
    if (!map) return
    const visible = new Set(BASE_LAYER_VISIBLE_LAYERS[baseLayer])
    for (const layerId of ALL_BASE_LAYER_IDS) {
      if (!map.getLayer(layerId)) continue
      map.setLayoutProperty(layerId, 'visibility', visible.has(layerId) ? 'visible' : 'none')
    }
  }, [map, baseLayer])

  return (
    <div className="glass-panel flex items-center gap-0.5 rounded-[var(--radius-control)] p-1">
      <Layers className="ml-1.5 mr-0.5 h-3.5 w-3.5 text-text-tertiary" />
      {LAYER_ORDER.map((id) => (
        <button
          key={id}
          onClick={() => setBaseLayer(id)}
          className={cn(
            'rounded-[6px] px-2.5 py-1.5 text-xs font-medium transition-colors',
            baseLayer === id
              ? 'bg-accent-500 text-canvas'
              : 'text-text-secondary hover:bg-surface-3 hover:text-text-primary',
          )}
        >
          {BASE_LAYER_LABELS[id]}
        </button>
      ))}
    </div>
  )
}
