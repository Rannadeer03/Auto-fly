import { useState } from 'react'
import { Library } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { Input, Textarea } from '@/components/ui/input'
import { useSaveManualToLibrary, useSaveToLibrary } from '@/features/mission-library/hooks/use-mission-library'
import { useMissionDraftStore } from '@/store/mission-draft-store'
import { useUiStore } from '@/store/ui-store'

interface SaveToLibraryButtonProps {
  disabled?: boolean
  iconOnly?: boolean
}

/** Saves the currently drawn + generated survey (or manual path) as a
 * reusable Mission Library entry — independent of uploading it to the
 * drone. Both save hooks are always called (rules of hooks) — only one is
 * ever actually invoked, based on missionMode. */
export function SaveToLibraryButton({ disabled, iconOnly }: SaveToLibraryButtonProps) {
  const [open, setOpen] = useState(false)
  const missionMode = useUiStore((s) => s.missionMode)
  const missionName = useMissionDraftStore((s) => s.flightParams.missionName)
  const missionDescription = useMissionDraftStore((s) => s.flightParams.missionDescription)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const saveSurvey = useSaveToLibrary()
  const saveManual = useSaveManualToLibrary()
  const save = missionMode === 'survey' ? saveSurvey : saveManual

  const openDialog = () => {
    setName(missionName || '')
    setDescription(missionDescription || '')
    setOpen(true)
  }

  const confirm = () => {
    if (!name.trim()) return
    save.mutate(
      { name, description },
      { onSuccess: () => setOpen(false) },
    )
  }

  return (
    <>
      <Button
        size="sm"
        variant={iconOnly ? 'ghost' : 'outline'}
        disabled={disabled}
        onClick={openDialog}
        title="Save to Library"
      >
        <Library className="h-3.5 w-3.5" />
        {!iconOnly && 'Save to Library'}
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogTitle>Save mission to library</DialogTitle>
          <DialogDescription>
            {missionMode === 'survey'
              ? 'Stores this survey (boundary, waypoints, altitude, speed, overlap, camera settings) so it can be reused later.'
              : 'Stores this manual mission (launch, home, and waypoints) so it can be reused later.'}
          </DialogDescription>
          <div className="mt-4 space-y-2">
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Mission name"
              autoFocus
            />
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Description (optional)"
              rows={3}
            />
          </div>
          <div className="mt-5 flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button variant="accent" onClick={confirm} disabled={!name.trim() || save.isPending}>
              Save
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
