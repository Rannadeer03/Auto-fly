import { lazy, Suspense } from 'react'
import { Loader2 } from 'lucide-react'
import { Sidebar } from '@/components/layout/sidebar'
import { TopStatusBar } from '@/components/layout/top-status-bar'
import { StatusBanner } from '@/components/feedback/status-banner'
import { MissionPage } from '@/pages/mission-page'
import { useUiStore } from '@/store/ui-store'

const TelemetryPage = lazy(() =>
  import('@/pages/telemetry-page').then((m) => ({ default: m.TelemetryPage })),
)
const DroneStatusPage = lazy(() =>
  import('@/pages/drone-status-page').then((m) => ({ default: m.DroneStatusPage })),
)
const CameraPage = lazy(() => import('@/pages/camera-page').then((m) => ({ default: m.CameraPage })))
const MissionFilesPage = lazy(() =>
  import('@/pages/mission-files-page').then((m) => ({ default: m.MissionFilesPage })),
)
const LogsPage = lazy(() => import('@/pages/logs-page').then((m) => ({ default: m.LogsPage })))
const SettingsPage = lazy(() =>
  import('@/pages/settings-page').then((m) => ({ default: m.SettingsPage })),
)

function PageFallback() {
  return (
    <div className="flex h-full items-center justify-center">
      <Loader2 className="h-6 w-6 animate-spin text-accent-400" />
    </div>
  )
}

export default function App() {
  const activeSection = useUiStore((s) => s.activeSection)
  const isMissionView = activeSection === 'mission' || activeSection === 'survey-settings'

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-canvas">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopStatusBar />
        <StatusBanner />
        <main className="relative min-h-0 flex-1">
          {/* Kept mounted across every section switch — recreating the
              MapLibre GL context (and losing the drawn farm boundary) every
              time the sidebar changes would be both slow and disorienting. */}
          <div className={isMissionView ? 'absolute inset-0' : 'hidden'}>
            <MissionPage />
          </div>

          {!isMissionView && (
            <Suspense fallback={<PageFallback />}>
              {activeSection === 'telemetry' && <TelemetryPage />}
              {activeSection === 'drone-status' && <DroneStatusPage />}
              {activeSection === 'camera' && <CameraPage />}
              {activeSection === 'mission-files' && <MissionFilesPage />}
              {activeSection === 'logs' && <LogsPage />}
              {activeSection === 'settings' && <SettingsPage />}
            </Suspense>
          )}
        </main>
      </div>
    </div>
  )
}
