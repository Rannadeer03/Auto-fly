import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { BaseLayerId } from '@/constants/map'

export type SidebarSection =
  | 'mission'
  | 'survey-settings'
  | 'telemetry'
  | 'drone-status'
  | 'camera'
  | 'mission-library'
  | 'mission-files'
  | 'logs'
  | 'settings'

interface UiState {
  activeSection: SidebarSection
  sidebarCollapsed: boolean
  baseLayer: BaseLayerId
  selectedWaypointIndex: number | null
  setActiveSection: (section: SidebarSection) => void
  toggleSidebar: () => void
  setBaseLayer: (layer: BaseLayerId) => void
  selectWaypoint: (index: number | null) => void
}

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      activeSection: 'mission',
      sidebarCollapsed: false,
      baseLayer: 'satellite',
      selectedWaypointIndex: null,
      setActiveSection: (section) => set({ activeSection: section }),
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setBaseLayer: (layer) => set({ baseLayer: layer }),
      selectWaypoint: (index) => set({ selectedWaypointIndex: index }),
    }),
    {
      name: 'vayuraksha-ui-prefs',
      // Only persist durable preferences — never the active section (always
      // boot into Mission) or the transient waypoint selection.
      partialize: (s) => ({ sidebarCollapsed: s.sidebarCollapsed, baseLayer: s.baseLayer }),
    },
  ),
)
