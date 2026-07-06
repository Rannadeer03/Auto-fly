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

export type MissionMode = 'survey' | 'manual'

interface UiState {
  activeSection: SidebarSection
  sidebarCollapsed: boolean
  baseLayer: BaseLayerId
  // Survey Mode selection — index into the backend-generated, never-
  // reordered survey path (SurveyLayer/WaypointDetailCard). Left untouched
  // by Manual Mode, which has its own id-based selection below — an array
  // index would go stale the moment Manual Mode supports reordering.
  selectedWaypointIndex: number | null
  // Manual Mode selection — a stable MissionItem.id (types/mission-items.ts),
  // not a position, since drag-reorder/insert (Phase 2B+) changes array
  // order but never an item's identity.
  selectedManualItemId: string | null
  missionMode: MissionMode
  setActiveSection: (section: SidebarSection) => void
  toggleSidebar: () => void
  setBaseLayer: (layer: BaseLayerId) => void
  selectWaypoint: (index: number | null) => void
  selectManualItem: (id: string | null) => void
  setMissionMode: (mode: MissionMode) => void
}

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      activeSection: 'mission',
      sidebarCollapsed: false,
      baseLayer: 'satellite',
      selectedWaypointIndex: null,
      selectedManualItemId: null,
      missionMode: 'survey',
      setActiveSection: (section) => set({ activeSection: section }),
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setBaseLayer: (layer) => set({ baseLayer: layer }),
      selectWaypoint: (index) => set({ selectedWaypointIndex: index }),
      selectManualItem: (id) => set({ selectedManualItemId: id }),
      setMissionMode: (mode) => set({ missionMode: mode, selectedWaypointIndex: null, selectedManualItemId: null }),
    }),
    {
      name: 'vayuraksha-ui-prefs',
      // Only persist durable preferences — never the active section (always
      // boot into Mission) or the transient waypoint selection.
      partialize: (s) => ({ sidebarCollapsed: s.sidebarCollapsed, baseLayer: s.baseLayer }),
    },
  ),
)
