/**
 * PlayerEditForm - inline edit form shown when a reviewer clicks the edit icon on a result.
 *
 * Renders a row per player with name, score, and races-played inputs, plus
 * add/remove row controls and save/cancel buttons.
 */

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Plus, Trash2 } from "lucide-react"
import type { BulkPlayer } from "@/lib/types"

interface PlayerEditFormProps {
  editedPlayers: BulkPlayer[]
  setEditedPlayers: (players: BulkPlayer[]) => void
  /** Called when a single field on a player row changes */
  onPlayerChange: (index: number, field: keyof BulkPlayer, value: string | number | boolean) => void
  onSave: () => void
  onCancel: () => void
}

export function PlayerEditForm({
  editedPlayers,
  setEditedPlayers,
  onPlayerChange,
  onSave,
  onCancel,
}: PlayerEditFormProps) {
  return (
    <>
      {editedPlayers.map((player, idx) => (
        <div key={player.id ?? String(idx)} className="flex gap-2 items-center">
          <Input
            value={player.name}
            onChange={(e) => onPlayerChange(idx, "name", e.target.value)}
            className="flex-1"
            placeholder="Player name"
          />
          <Input
            type="text"
            inputMode="numeric"
            value={player.score}
            onChange={(e) => {
              const value = e.target.value
              if (value === "" || /^\d+$/.test(value)) {
                onPlayerChange(idx, "score", value === "" ? 0 : parseInt(value))
              }
            }}
            className="w-24"
            placeholder="Score"
          />
          <Input
            type="text"
            inputMode="numeric"
            value={player.races_played}
            onChange={(e) => {
              const value = e.target.value
              if (value === "" || /^\d+$/.test(value)) {
                onPlayerChange(idx, "races_played", value === "" ? 0 : parseInt(value))
              }
            }}
            className="w-16"
            placeholder="Races"
          />
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setEditedPlayers(editedPlayers.filter((_, i) => i !== idx))}
            title="Remove player"
            aria-label={`Remove player ${player.name || idx + 1}`}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      ))}

      {/* Add a blank player row */}
      <Button
        variant="outline"
        className="w-full"
        onClick={() =>
          setEditedPlayers([
            ...editedPlayers,
            { id: crypto.randomUUID(), name: "", score: 0, is_roster_member: false, races_played: 12 },
          ])
        }
      >
        <Plus className="h-4 w-4 mr-2" />
        Add Player
      </Button>

      <div className="flex justify-end gap-2 pt-2">
        <Button variant="outline" size="sm" onClick={onCancel}>
          Cancel
        </Button>
        <Button size="sm" onClick={onSave}>
          Save
        </Button>
      </div>
    </>
  )
}
