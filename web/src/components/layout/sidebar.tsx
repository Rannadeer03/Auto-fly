import {
  Map,
  SlidersHorizontal,
  Activity,
  Radio,
  Camera,
  LibraryBig,
  FolderOpen,
  ScrollText,
  Settings,
  ChevronsLeft,
  ChevronsRight,
} from 'lucide-react'
import { motion } from 'framer-motion'
import { useUiStore, type SidebarSection } from '@/store/ui-store'
import { cn } from '@/utils/cn'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

const NAV_ITEMS: { id: SidebarSection; label: string; icon: typeof Map }[] = [
  { id: 'mission', label: 'Mission', icon: Map },
  { id: 'survey-settings', label: 'Survey Settings', icon: SlidersHorizontal },
  { id: 'telemetry', label: 'Telemetry', icon: Activity },
  { id: 'drone-status', label: 'Drone Status', icon: Radio },
  { id: 'camera', label: 'Camera', icon: Camera },
  { id: 'mission-library', label: 'Mission Library', icon: LibraryBig },
  { id: 'mission-files', label: 'Mission Files', icon: FolderOpen },
  { id: 'logs', label: 'Logs', icon: ScrollText },
  { id: 'settings', label: 'Settings', icon: Settings },
]

export function Sidebar() {
  const activeSection = useUiStore((s) => s.activeSection)
  const setActiveSection = useUiStore((s) => s.setActiveSection)
  const collapsed = useUiStore((s) => s.sidebarCollapsed)
  const toggleSidebar = useUiStore((s) => s.toggleSidebar)

  return (
    <motion.nav
      animate={{ width: collapsed ? 64 : 208 }}
      transition={{ duration: 0.18, ease: 'easeOut' }}
      className="flex h-full shrink-0 flex-col border-r border-border bg-surface"
    >
      <div className="flex h-14 items-center gap-2 border-b border-border px-4">
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-accent-500/15">
          <span className="text-sm font-bold text-accent-400">V</span>
        </div>
        {!collapsed && (
          <span className="truncate text-sm font-semibold tracking-tight text-text-primary">
            Vayuraksha
          </span>
        )}
      </div>

      <div className="flex-1 space-y-1 overflow-y-auto py-3">
        {NAV_ITEMS.map((item) => (
          <NavButton
            key={item.id}
            item={item}
            active={activeSection === item.id}
            collapsed={collapsed}
            onClick={() => setActiveSection(item.id)}
          />
        ))}
      </div>

      <button
        onClick={toggleSidebar}
        className="flex h-11 items-center justify-center border-t border-border text-text-tertiary transition-colors hover:bg-surface-2 hover:text-text-primary"
        aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
      >
        {collapsed ? <ChevronsRight className="h-4 w-4" /> : <ChevronsLeft className="h-4 w-4" />}
      </button>
    </motion.nav>
  )
}

function NavButton({
  item,
  active,
  collapsed,
  onClick,
}: {
  item: (typeof NAV_ITEMS)[number]
  active: boolean
  collapsed: boolean
  onClick: () => void
}) {
  const Icon = item.icon
  const button = (
    <button
      onClick={onClick}
      className={cn(
        'relative mx-2 flex h-10 items-center gap-3 rounded-[var(--radius-control)] px-3 text-sm transition-colors',
        active
          ? 'bg-accent-500/12 text-accent-400'
          : 'text-text-secondary hover:bg-surface-2 hover:text-text-primary',
      )}
    >
      {active && (
        <motion.span
          layoutId="sidebar-active-indicator"
          className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-full bg-accent-500"
          transition={{ duration: 0.15 }}
        />
      )}
      <Icon className="h-[18px] w-[18px] shrink-0" />
      {!collapsed && <span className="truncate font-medium">{item.label}</span>}
    </button>
  )

  if (!collapsed) return button

  return (
    <Tooltip>
      <TooltipTrigger asChild>{button}</TooltipTrigger>
      <TooltipContent side="right">{item.label}</TooltipContent>
    </Tooltip>
  )
}
