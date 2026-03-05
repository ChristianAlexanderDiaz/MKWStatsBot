/**
 * ReviewHeader - sticky top bar for the bulk review page.
 *
 * Shows the session title, per-status counts (approved / pending / rejected),
 * the staged-players badge+menu, approve-all shortcut, and the final save button.
 */

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Check, CheckCircle2, Clock, Loader2, Save, X } from "lucide-react"
import { StagedPlayersMenu } from "./StagedPlayersMenu"
import type { BulkSession, StagedPlayer } from "@/lib/types"

interface ReviewHeaderProps {
  session: BulkSession
  approvedCount: number
  pendingCount: number
  rejectedCount: number
  stagedPlayers: StagedPlayer[]
  showStagedMenu: boolean
  setShowStagedMenu: (open: boolean) => void
  onRemoveStagedPlayer: (playerName: string) => Promise<void>
  isSaving: boolean
  onConfirmAndSave: () => void
  onApproveAll: () => void
}

export function ReviewHeader({
  session,
  approvedCount,
  pendingCount,
  rejectedCount,
  stagedPlayers,
  showStagedMenu,
  setShowStagedMenu,
  onRemoveStagedPlayer,
  isSaving,
  onConfirmAndSave,
  onApproveAll,
}: ReviewHeaderProps) {
  return (
    <>
      {/* Sticky top bar */}
      <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur">
        <div className="max-w-[1400px] mx-auto px-6 flex h-14 items-center justify-between">
          <div>
            <h1 className="font-bold">Bulk Scan Review</h1>
            <p className="text-xs text-muted-foreground">
              {session.total_images} images to review
            </p>
          </div>

          <div className="flex items-center gap-4">
            {/* Per-status badges */}
            <div className="flex items-center gap-2 text-sm">
              <Badge variant="success" className="gap-1" aria-label={`Approved: ${approvedCount}`}>
                <CheckCircle2 className="h-3 w-3" />
                {approvedCount}
              </Badge>
              <Badge variant="secondary" className="gap-1" aria-label={`Pending: ${pendingCount}`}>
                <Clock className="h-3 w-3" />
                {pendingCount}
              </Badge>
              <Badge variant="destructive" className="gap-1" aria-label={`Rejected: ${rejectedCount}`}>
                <X className="h-3 w-3" />
                {rejectedCount}
              </Badge>

              {/* Staged-players menu — only shown when at least one player is staged */}
              {stagedPlayers.length > 0 && (
                <StagedPlayersMenu
                  stagedPlayers={stagedPlayers}
                  showStagedMenu={showStagedMenu}
                  setShowStagedMenu={setShowStagedMenu}
                  onRemoveStagedPlayer={onRemoveStagedPlayer}
                />
              )}
            </div>

            {/* Save button — disabled until at least one result is approved */}
            <Button
              onClick={onConfirmAndSave}
              disabled={approvedCount === 0 || isSaving}
              className="gap-2"
            >
              {isSaving ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Save className="h-4 w-4" />
              )}
              Save {approvedCount} {approvedCount === 1 ? "War" : "Wars"}
            </Button>
          </div>
        </div>
      </header>

      {/* Secondary actions bar */}
      <div className="border-b bg-muted/50">
        <div className="max-w-[1400px] mx-auto px-6 py-2 flex items-center gap-4">
          <Button variant="outline" size="sm" onClick={onApproveAll} disabled={isSaving || pendingCount === 0}>
            <Check className="mr-2 h-4 w-4" />
            Approve All Pending
          </Button>
          <span className="text-sm text-muted-foreground">
            Review each war below. Click player names to edit or add to roster.
          </span>
        </div>
      </div>
    </>
  )
}
