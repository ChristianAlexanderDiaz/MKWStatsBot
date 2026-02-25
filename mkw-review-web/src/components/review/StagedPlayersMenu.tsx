/**
 * StagedPlayersMenu - badge + dropdown that shows players queued for roster creation.
 *
 * Players are "staged" locally when the reviewer clicks "Add as New" on an unknown
 * name.  They are not written to the DB until the session is confirmed.  This menu
 * lets reviewers inspect or remove staged entries before that happens.
 */

import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ChevronDown, UserPlus, X } from "lucide-react"
import type { StagedPlayer } from "@/lib/types"

interface StagedPlayersMenuProps {
  stagedPlayers: StagedPlayer[]
  showStagedMenu: boolean
  setShowStagedMenu: (open: boolean) => void
  /** Async because removal must revert is_roster_member in affected results */
  onRemoveStagedPlayer: (playerName: string) => Promise<void>
}

export function StagedPlayersMenu({
  stagedPlayers,
  showStagedMenu,
  setShowStagedMenu,
  onRemoveStagedPlayer,
}: StagedPlayersMenuProps) {
  return (
    <div className="relative">
      {/* Clickable badge that toggles the dropdown */}
      <Badge
        variant="outline"
        className="gap-1 border-blue-500 text-blue-600 cursor-pointer hover:bg-blue-50 dark:hover:bg-blue-950/30 transition-colors"
        onClick={() => setShowStagedMenu(!showStagedMenu)}
      >
        <UserPlus className="h-3 w-3" />
        {stagedPlayers.length} staged
        <ChevronDown
          className={`h-3 w-3 transition-transform ${showStagedMenu ? "rotate-180" : ""}`}
        />
      </Badge>

      {showStagedMenu && (
        <>
          {/* Invisible backdrop — clicking it closes the menu */}
          <div
            className="fixed inset-0 z-40"
            onClick={() => setShowStagedMenu(false)}
            onKeyDown={(e) => {
              if (e.key === "Escape" || e.key === "Enter" || e.key === " ") {
                setShowStagedMenu(false)
              }
            }}
            role="button"
            tabIndex={0}
            aria-label="Close staged players menu"
          />

          {/* Dropdown */}
          <div className="absolute right-0 top-full mt-2 w-80 bg-background border rounded-md shadow-lg z-50 overflow-hidden">
            <div className="p-3 border-b bg-muted/50 flex items-start justify-between">
              <div>
                <h3 className="font-semibold text-sm">Staged Players</h3>
                <p className="text-xs text-muted-foreground mt-1">
                  These players will be added to your roster when you save
                </p>
              </div>
              <Button
                variant="ghost"
                size="sm"
                className="h-6 w-6 p-0 -mt-1"
                onClick={(e) => {
                  e.stopPropagation()
                  setShowStagedMenu(false)
                }}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>

            <div className="max-h-96 overflow-y-auto">
              {stagedPlayers.length === 0 ? (
                <div className="p-6 text-center text-sm text-muted-foreground">
                  No staged players
                </div>
              ) : (
                stagedPlayers.map((player) => (
                  <div
                    key={player.name}
                    className="flex items-center justify-between p-3 border-b last:border-b-0 hover:bg-muted/50 transition-colors"
                  >
                    <div className="flex-1">
                      <div className="font-medium text-sm">{player.name}</div>
                      <div className="text-xs text-muted-foreground capitalize">
                        {player.memberStatus}
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-8 w-8 p-0 text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-950/30"
                      onClick={(e) => {
                        e.stopPropagation()
                        onRemoveStagedPlayer(player.name)
                      }}
                      title="Remove from staged"
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                ))
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
