/**
 * FailureCard - displays an image the OCR pipeline could not parse.
 *
 * In view mode: shows the error message and buttons to edit manually or reject.
 * In edit mode: shows a player-entry form so the reviewer can rescue the data
 *   by manually typing names/scores, then save as pending or approved.
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { AlertCircle, Check, Edit2, Loader2, Plus, Save, Trash2, X } from "lucide-react"
import type { BulkFailure, BulkPlayer } from "@/lib/types"

interface FailureCardProps {
  failure: BulkFailure
  editingFailure: number | null
  failureEditedPlayers: BulkPlayer[]
  onEditFailure: (failureId: number) => void
  onCancelEditFailure: () => void
  onPlayerChange: (index: number, field: keyof BulkPlayer, value: string | number | boolean) => void
  onAddPlayer: () => void
  onRemovePlayer: (index: number) => void
  onSaveFailure: (failureId: number, status: "pending" | "approved" | "rejected") => void
  /** Forwarded from the convertFailureMutation so we can show a spinner */
  convertIsPending: boolean
}

export function FailureCard({
  failure,
  editingFailure,
  failureEditedPlayers,
  onEditFailure,
  onCancelEditFailure,
  onPlayerChange,
  onAddPlayer,
  onRemovePlayer,
  onSaveFailure,
  convertIsPending,
}: FailureCardProps) {
  const isEditingThis = editingFailure === failure.id

  return (
    <Card className="border-red-500/30 bg-red-50/30 dark:bg-red-950/10">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CardTitle className="text-lg text-red-600 dark:text-red-400">
              Failed to Process
            </CardTitle>
            <Badge variant="destructive">Error</Badge>
          </div>
          {!isEditingThis && (
            <Button variant="outline" size="sm" onClick={() => onEditFailure(failure.id)}>
              <Edit2 className="h-4 w-4 mr-1" />
              Edit Manually
            </Button>
          )}
        </div>
        <CardDescription>
          {failure.message_timestamp
            ? new Date(failure.message_timestamp).toLocaleString()
            : "Unknown time"}
        </CardDescription>
      </CardHeader>

      <CardContent>
        <div className="flex flex-col md:flex-row gap-6">
          {/* Preview image (or placeholder) */}
          <div className="w-full md:w-[600px] flex-shrink-0">
            {failure.image_url ? (
              <img
                src={failure.image_url}
                alt="Failed"
                className="w-full h-auto rounded-md border border-red-300"
              />
            ) : (
              <div className="w-full aspect-video bg-muted rounded-md flex items-center justify-center border border-red-300">
                <p className="text-sm text-muted-foreground">No image</p>
              </div>
            )}
          </div>

          {/* Right panel: edit form or error display */}
          <div className="flex-1">
            {isEditingThis ? (
              // ---- Manual entry form ----
              <div className="space-y-3">
                <p className="text-sm text-muted-foreground mb-2">
                  Manually enter the players from this image:
                </p>

                {failureEditedPlayers.map((player, index) => (
                  <div key={index} className="flex items-center gap-2">
                    <Input
                      placeholder="Player name"
                      value={player.name}
                      onChange={(e) => onPlayerChange(index, "name", e.target.value)}
                      className="flex-1"
                    />
                    <Input
                      type="number"
                      placeholder="Score"
                      value={player.score || ""}
                      onChange={(e) =>
                        onPlayerChange(index, "score", parseInt(e.target.value) || 0)
                      }
                      className="w-20"
                    />
                    <Input
                      type="text"
                      inputMode="numeric"
                      placeholder="Races"
                      value={player.races_played}
                      onChange={(e) => {
                        const value = e.target.value
                        if (value === "" || /^\d+$/.test(value)) {
                          onPlayerChange(index, "races_played", value === "" ? 0 : parseInt(value))
                        }
                      }}
                      className="w-16"
                    />
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => onRemovePlayer(index)}
                      disabled={failureEditedPlayers.length <= 1}
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </div>
                ))}

                <Button variant="outline" size="sm" onClick={onAddPlayer} className="w-full">
                  <Plus className="h-4 w-4 mr-1" />
                  Add Player
                </Button>

                <div className="flex gap-2 mt-4">
                  <Button variant="outline" size="sm" onClick={onCancelEditFailure}>
                    Cancel
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => onSaveFailure(failure.id, "pending")}
                    disabled={convertIsPending}
                  >
                    {convertIsPending ? (
                      <Loader2 className="h-4 w-4 animate-spin mr-1" />
                    ) : (
                      <Save className="h-4 w-4 mr-1" />
                    )}
                    Save
                  </Button>
                  <Button
                    size="sm"
                    variant="default"
                    className="bg-green-600 hover:bg-green-700"
                    onClick={() => onSaveFailure(failure.id, "approved")}
                    disabled={convertIsPending}
                  >
                    <Check className="h-4 w-4 mr-1" />
                    Save & Approve
                  </Button>
                </div>
              </div>
            ) : (
              // ---- Error display ----
              <>
                <div className="border border-dashed border-red-300 rounded-md p-6 bg-background">
                  <div className="flex items-start gap-3">
                    <AlertCircle className="h-5 w-5 text-red-500 mt-0.5" />
                    <div className="flex-1">
                      <p className="font-medium text-red-600 mb-2">Processing Error</p>
                      <p className="text-sm text-muted-foreground">{failure.error_message}</p>
                    </div>
                  </div>
                </div>

                <div className="flex gap-2 mt-4">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => onEditFailure(failure.id)}
                  >
                    <Edit2 className="h-4 w-4 mr-1" />
                    Edit Manually
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-red-600 hover:text-red-700"
                    onClick={() => onSaveFailure(failure.id, "rejected")}
                    disabled={convertIsPending}
                  >
                    <X className="h-4 w-4 mr-1" />
                    Reject
                  </Button>
                </div>

                <p className="text-xs text-muted-foreground mt-3 italic">
                  Note: Failed images won&apos;t be saved. You can reject or edit manually to add
                  players.
                </p>
              </>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
