/**
 * WarResultCard - displays a single OCR result (one war table) for review.
 *
 * In view mode: shows players colour-coded by roster membership.  Unknown
 * players get "Link" (map to an existing roster name) and "Add as New"
 * (queue a brand-new player for creation on confirm) buttons.
 *
 * In edit mode: delegates to PlayerEditForm so the reviewer can correct
 * names/scores/races before approving.
 */

import { useMemo, useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Check, Edit2, Link2, UserPlus, X } from "lucide-react"
import { PlayerEditForm } from "./PlayerEditForm"
import type { BulkResult, BulkPlayer } from "@/lib/types"

interface WarResultCardProps {
  result: BulkResult
  /** 0-based position in the results array, used for "Table N / total" heading */
  index: number
  totalResults: number
  // ---- edit state ----
  editingResult: number | null
  editedPlayers: BulkPlayer[]
  setEditedPlayers: (players: BulkPlayer[]) => void
  setEditingResult: (id: number | null) => void
  // ---- link-player state ----
  linkingPlayer: { resultId: number; playerIndex: number; playerName: string } | null
  setLinkingPlayer: (lp: { resultId: number; playerIndex: number; playerName: string } | null) => void
  linkSearchQuery: string
  setLinkSearchQuery: (q: string) => void
  // ---- add-new-player state ----
  addingNewPlayer: { resultId: number; playerIndex: number; playerName: string } | null
  setAddingNewPlayer: (ap: { resultId: number; playerIndex: number; playerName: string } | null) => void
  newPlayerFormData: { name: string; memberStatus: string }
  setNewPlayerFormData: (data: { name: string; memberStatus: string }) => void
  // ---- derived / shared ----
  newlyAddedPlayers: Set<string>
  allAvailablePlayers: string[]
  totalScore: (players: BulkPlayer[]) => number
  // ---- handlers ----
  onApprove: (resultId: number) => void
  onReject: (resultId: number) => void
  onEdit: (result: BulkResult) => void
  onSaveEdit: (resultId: number) => void
  onPlayerChange: (index: number, field: keyof BulkPlayer, value: string | number | boolean) => void
  onLinkPlayer: (resultId: number, playerIndex: number, detectedName: string, rosterPlayerName: string) => Promise<void>
  onAddNewPlayer: (resultId: number, playerIndex: number, name: string, memberStatus: string) => void
}

export function WarResultCard({
  result,
  index,
  totalResults,
  editingResult,
  editedPlayers,
  setEditedPlayers,
  setEditingResult,
  linkingPlayer,
  setLinkingPlayer,
  linkSearchQuery,
  setLinkSearchQuery,
  addingNewPlayer,
  setAddingNewPlayer,
  newPlayerFormData,
  setNewPlayerFormData,
  newlyAddedPlayers,
  allAvailablePlayers,
  totalScore,
  onApprove,
  onReject,
  onEdit,
  onSaveEdit,
  onPlayerChange,
  onLinkPlayer,
  onAddNewPlayer,
}: WarResultCardProps) {
  const players = result.corrected_players || result.detected_players
  const isEditing = editingResult === result.id
  const [linkError, setLinkError] = useState<string | null>(null)

  const filteredPlayers = useMemo(
    () =>
      allAvailablePlayers.filter(
        (name) =>
          linkSearchQuery === "" ||
          name.toLowerCase().includes(linkSearchQuery.toLowerCase())
      ),
    [allAvailablePlayers, linkSearchQuery]
  )

  // Border/background tint depending on review status
  const cardClassName = `transition-all ${
    result.review_status === "approved"
      ? "border-green-500/50 bg-green-50/50 dark:bg-green-950/20"
      : result.review_status === "rejected"
      ? "border-red-500/50 bg-red-50/50 dark:bg-red-950/20"
      : ""
  }`

  return (
    <Card className={cardClassName}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CardTitle className="text-lg">
              Table {index + 1}/{totalResults}
            </CardTitle>
            <Badge
              variant={
                result.review_status === "approved"
                  ? "success"
                  : result.review_status === "rejected"
                  ? "destructive"
                  : "secondary"
              }
            >
              {result.review_status}
            </Badge>
          </div>

          {/* Approve / reject / edit controls — hidden while editing */}
          {!isEditing && (
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" onClick={() => onEdit(result)}
                aria-label={`Edit result ${result.id}`} title="Edit result">
                <Edit2 className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="text-green-600 hover:text-green-700"
                onClick={() => onApprove(result.id)}
                aria-label={`Approve result ${result.id}`}
                title="Approve result"
              >
                <Check className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="text-red-600 hover:text-red-700"
                onClick={() => onReject(result.id)}
                aria-label={`Reject result ${result.id}`}
                title="Reject result"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          )}
        </div>

        <CardDescription>
          {result.image_filename && (
            <span className="text-xs text-muted-foreground">
              {result.image_filename}
              <br />
            </span>
          )}
          {result.message_timestamp
            ? new Date(result.message_timestamp).toLocaleString()
            : "Unknown time"}{" "}
          | {players.length} players | Team Score: {totalScore(players)}
        </CardDescription>
      </CardHeader>

      <CardContent>
        <div className="flex flex-col md:flex-row gap-6">
          {/* Left: preview image */}
          <div className="w-full md:w-[600px] flex-shrink-0">
            {result.image_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={result.image_url}
                alt={`Table ${index + 1}`}
                className="w-full h-auto rounded-md border"
              />
            ) : (
              <div className="w-full aspect-video bg-muted rounded-md flex items-center justify-center">
                <p className="text-sm text-muted-foreground">No image</p>
              </div>
            )}
          </div>

          {/* Right: player list / edit form */}
          <div className="flex-1 space-y-2">
            {isEditing ? (
              <PlayerEditForm
                editedPlayers={editedPlayers}
                setEditedPlayers={setEditedPlayers}
                onPlayerChange={onPlayerChange}
                onSave={() => onSaveEdit(result.id)}
                onCancel={() => {
                  setEditingResult(null)
                  setEditedPlayers([])
                }}
              />
            ) : (
              <>
                {players.map((player, idx) => (
                  <div key={idx}>
                    {/* Player row */}
                    <div
                      className={`flex justify-between items-center p-3 rounded-md ${
                        player.is_roster_member
                          ? "bg-muted/50"
                          : "bg-yellow-100 dark:bg-yellow-900/30 border border-yellow-300"
                      }`}
                    >
                      <div className="flex items-center gap-2 flex-1">
                        <span
                          className={
                            !player.is_roster_member
                              ? "text-yellow-700 dark:text-yellow-400 font-medium"
                              : ""
                          }
                        >
                          {player.name}
                        </span>
                        {/* "New" badge for players that were just staged */}
                        {newlyAddedPlayers.has(player.name) && (
                          <Badge variant="success" className="text-xs">
                            New
                          </Badge>
                        )}
                      </div>

                      <div className="flex items-center gap-2 mr-2">
                        <span className="font-semibold">{player.score}</span>
                        <span className="text-xs text-muted-foreground">
                          ({player.races_played ?? result.race_count ?? 12}/
                          {result.race_count ?? 12} races)
                        </span>
                      </div>

                      {/* Link / Add as New buttons for unknown players */}
                      {!player.is_roster_member && (
                        <div className="flex items-center gap-1">
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-7 text-xs"
                            onClick={() => {
                              setLinkingPlayer({ resultId: result.id, playerIndex: idx, playerName: player.name })
                              setLinkSearchQuery("")
                              setAddingNewPlayer(null)
                            }}
                          >
                            <Link2 className="h-3 w-3 mr-1" />
                            Link
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-7 text-xs"
                            onClick={() => {
                              setAddingNewPlayer({ resultId: result.id, playerIndex: idx, playerName: player.name })
                              setNewPlayerFormData({ name: player.name, memberStatus: "ally" })
                              setLinkingPlayer(null)
                            }}
                          >
                            <UserPlus className="h-3 w-3 mr-1" />
                            Add as New
                          </Button>
                        </div>
                      )}
                    </div>

                    {/* Inline link-to-roster panel */}
                    {linkingPlayer?.resultId === result.id &&
                      linkingPlayer?.playerIndex === idx && (
                        <div className="mt-2 p-3 bg-background border rounded-md">
                          <label className="text-sm font-medium mb-2 block">
                            Link to Existing Roster Player
                          </label>
                          <div className="space-y-2">
                            <Input
                              value={linkSearchQuery}
                              onChange={(e) => setLinkSearchQuery(e.target.value)}
                              placeholder="Search roster players..."
                              className="w-full"
                            />
                            <div className="max-h-40 overflow-y-auto border rounded-md">
                              {filteredPlayers.map((name) => (
                                <button
                                  key={name}
                                  className="w-full px-3 py-2 text-left text-sm hover:bg-muted border-b last:border-b-0"
                                  onClick={async () => {
                                    try {
                                      setLinkError(null)
                                      await onLinkPlayer(result.id, idx, player.name, name)
                                    } catch (err) {
                                      const msg = err instanceof Error ? err.message : "Unknown error"
                                      setLinkError(`Failed to link player: ${msg}`)
                                    }
                                  }}
                                >
                                  {name}
                                </button>
                              ))}
                              {filteredPlayers.length === 0 && (
                                <div className="px-3 py-2 text-sm text-muted-foreground">
                                  No players found
                                </div>
                              )}
                              {linkError && (
                                <div className="px-3 py-2 text-xs text-red-600">
                                  {linkError}
                                </div>
                              )}
                            </div>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => {
                                setLinkingPlayer(null)
                                setLinkSearchQuery("")
                              }}
                            >
                              Cancel
                            </Button>
                          </div>
                        </div>
                      )}

                    {/* Inline add-new-player panel */}
                    {addingNewPlayer?.resultId === result.id &&
                      addingNewPlayer?.playerIndex === idx && (
                        <div className="mt-2 p-3 bg-background border rounded-md">
                          <label className="text-sm font-medium mb-2 block">
                            Add as New Player to Roster
                          </label>
                          <div className="space-y-2">
                            <Input
                              value={newPlayerFormData.name}
                              onChange={(e) =>
                                setNewPlayerFormData({ ...newPlayerFormData, name: e.target.value })
                              }
                              placeholder="Player name"
                              className="w-full"
                            />
                            <select
                              className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm"
                              value={newPlayerFormData.memberStatus}
                              onChange={(e) =>
                                setNewPlayerFormData({
                                  ...newPlayerFormData,
                                  memberStatus: e.target.value,
                                })
                              }
                            >
                              <option value="member">Member</option>
                              <option value="trial">Trial</option>
                              <option value="ally">Ally</option>
                              <option value="kicked">Kicked</option>
                            </select>
                            <div className="flex gap-2">
                              <Button
                                size="sm"
                                onClick={() =>
                                  onAddNewPlayer(
                                    result.id,
                                    idx,
                                    newPlayerFormData.name,
                                    newPlayerFormData.memberStatus
                                  )
                                }
                                disabled={!newPlayerFormData.name.trim()}
                              >
                                Stage Player
                              </Button>
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => {
                                  setAddingNewPlayer(null)
                                  setNewPlayerFormData({ name: "", memberStatus: "ally" })
                                }}
                              >
                                Cancel
                              </Button>
                            </div>
                          </div>
                        </div>
                      )}
                  </div>
                ))}

                {/* Warning hint if any player is not in the roster */}
                {players.some((p) => !p.is_roster_member) && (
                  <p className="text-xs text-yellow-600 dark:text-yellow-500 mt-2">
                    Yellow = not in roster. Use &quot;Link&quot; to connect to existing player, or &quot;Add as
                    New&quot; to create new.
                  </p>
                )}
              </>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
