import { UploadCloud, Trash2, CheckCircle2, AlertCircle } from 'lucide-react'
import { Panel } from '@/components/ui/panel'
import { Button } from '@/components/ui/button'
import { useMissionDraftStore } from '@/store/mission-draft-store'
import { useUploadMission, useClearMission } from '@/features/mission-execution/hooks/use-upload-mission'

export function UploadMissionBar() {
  const generated = useMissionDraftStore((s) => s.generated)
  const farmPolygon = useMissionDraftStore((s) => s.farmPolygon)
  const upload = useUploadMission()
  const clear = useClearMission()

  const canUpload = Boolean(farmPolygon && farmPolygon.length >= 3)

  return (
    <Panel className="flex w-80 items-center justify-between px-3 py-2.5">
      <div className="flex items-center gap-2 text-xs">
        {generated?.uploaded_to_drone ? (
          generated.verified ? (
            <span className="flex items-center gap-1.5 text-success-500">
              <CheckCircle2 className="h-3.5 w-3.5" /> Uploaded &amp; verified
            </span>
          ) : (
            <span className="flex items-center gap-1.5 text-warning-500">
              <AlertCircle className="h-3.5 w-3.5" /> Uploaded, unverified
            </span>
          )
        ) : (
          <span className="text-text-tertiary">Not uploaded to drone</span>
        )}
      </div>
      <div className="flex items-center gap-1.5">
        <Button size="sm" variant="ghost" onClick={() => clear.mutate()} disabled={clear.isPending}>
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
        <Button
          size="sm"
          variant="accent"
          disabled={!canUpload || upload.isPending}
          onClick={() => upload.mutate()}
        >
          <UploadCloud className="h-3.5 w-3.5" />
          Upload Mission
        </Button>
      </div>
    </Panel>
  )
}
