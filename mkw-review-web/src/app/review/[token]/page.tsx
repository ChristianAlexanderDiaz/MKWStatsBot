"use client"

import { api, BulkResult, BulkPlayer } from "@/lib/api"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { useState, useEffect } from "react"
import { useParams, useRouter } from "next/navigation"
import {
  Check,
  X,
  Edit2,
  UserPlus,
  Save,
  AlertCircle,
  CheckCircle2,
  Clock,
  Loader2,
  Plus,
  Trash2,
  Link2
} from "lucide-react"

export default function BulkReviewPage() {
  const params = useParams()
  const router = useRouter()
  const token = params.token as string
  const queryClient = useQueryClient()

  const [editingResult, setEditingResult] = useState<number | null>(null)
  const [editedPlayers, setEditedPlayers] = useState<BulkPlayer[]>([])
  const [showAddPlayer, setShowAddPlayer] = useState<{ resultId: number; index: number } | null>(null)
  const [newPlayerName, setNewPlayerName] = useState("")
  const [isSaving, setIsSaving] = useState(false)
  const [linkingPlayer, setLinkingPlayer] = useState<{ resultId: number; playerIndex: number; playerName: string } | null>(null)
  const [rosterPlayers, setRosterPlayers] = useState<string[]>([])
  const [selectedRosterPlayer, setSelectedRosterPlayer] = useState<string>("")
  const [addingNewPlayer, setAddingNewPlayer] = useState<{ resultId: number; playerIndex: number; playerName: string } | null>(null)
  const [newPlayerFormData, setNewPlayerFormData] = useState<{ name: string; memberStatus: string }>({ name: "", memberStatus: "member" })
  const [isAddingPlayer, setIsAddingPlayer] = useState(false)
  const [newlyAddedPlayers, setNewlyAddedPlayers] = useState<Set<string>>(new Set())

  const { data, isLoading, error } = useQuery({
    queryKey: ["bulk-review", token],
    queryFn: () => api.getBulkResults(token),
    refetchInterval: false,
  })

  // Fetch roster players for linking functionality
  const refreshRosterPlayers = async () => {
    if (data?.session?.guild_id) {
      try {
        console.log('Fetching roster for guild_id:', data.session.guild_id)
        const result = await api.getPlayers(data.session.guild_id.toString())
        console.log('Roster API response:', result)
        const playerNames = result.players.map((p: any) => p.player_name)
        console.log('Roster player names:', playerNames)
        setRosterPlayers(playerNames)
      } catch (err) {
        console.error("Failed to fetch roster:", err)
      }
    } else {
      console.warn('Cannot fetch roster: guild_id not available', data?.session)
    }
  }

  useEffect(() => {
    refreshRosterPlayers()
  }, [data?.session?.guild_id])

  const updateResultMutation = useMutation({
    mutationFn: ({
      resultId,
      status,
      corrected,
    }: {
      resultId: number
      status: "pending" | "approved" | "rejected"
      corrected?: BulkPlayer[]
    }) => api.updateBulkResult(token, resultId, status, corrected),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["bulk-review", token] })
    },
  })

  const confirmMutation = useMutation({
    mutationFn: () => api.confirmBulkSession(token),
    onSuccess: (result) => {
      if (result) {
        alert(`Successfully created ${result.wars_created} wars!`)
        router.push("/dashboard")
      }
    },
  })

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto mb-4"></div>
          <p className="text-muted-foreground">Loading review session...</p>
        </div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-destructive">
              <AlertCircle className="h-5 w-5" />
              Session Not Found
            </CardTitle>
            <CardDescription>
              This review session may have expired or been completed.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button onClick={() => router.push("/")} className="w-full">
              Go to Dashboard
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  const { session, results } = data
  const approvedCount = results.filter((r) => r.review_status === "approved").length
  const pendingCount = results.filter((r) => r.review_status === "pending").length
  const rejectedCount = results.filter((r) => r.review_status === "rejected").length

  const handleApprove = (resultId: number) => {
    updateResultMutation.mutate({ resultId, status: "approved" })
  }

  const handleReject = (resultId: number) => {
    updateResultMutation.mutate({ resultId, status: "rejected" })
  }

  const handleEdit = (result: BulkResult) => {
    setEditingResult(result.id)
    setEditedPlayers(result.corrected_players || result.detected_players)
  }

  const handleSaveEdit = (resultId: number) => {
    updateResultMutation.mutate({
      resultId,
      status: "approved",
      corrected: editedPlayers,
    })
    setEditingResult(null)
    setEditedPlayers([])
  }

  const handlePlayerChange = (index: number, field: keyof BulkPlayer, value: string | number) => {
    const updated = [...editedPlayers]
    updated[index] = { ...updated[index], [field]: value }
    setEditedPlayers(updated)
  }

  const handleApproveAll = () => {
    results
      .filter((r) => r.review_status === "pending")
      .forEach((r) => {
        updateResultMutation.mutate({ resultId: r.id, status: "approved" })
      })
  }

  const handleConfirmAndSave = async () => {
    setIsSaving(true)
    await confirmMutation.mutateAsync()
    setIsSaving(false)
  }

  const handleLinkPlayer = async (resultId: number, playerIndex: number, detectedName: string, rosterPlayerName: string) => {
    if (!data?.session?.guild_id || !rosterPlayerName) return

    try {
      // Add the detected name as a nickname to the roster player
      const success = await api.addNickname(
        data.session.guild_id.toString(),
        rosterPlayerName,
        detectedName
      )

      if (success) {
        // Update the result to use the canonical roster name
        const result = results.find(r => r.id === resultId)
        if (result) {
          const players = result.corrected_players || result.detected_players
          const updatedPlayers = players.map((p, idx) =>
            idx === playerIndex
              ? { ...p, name: rosterPlayerName, is_roster_member: true }
              : p
          )

          // Update via mutation
          updateResultMutation.mutate({
            resultId,
            status: result.review_status,
            corrected: updatedPlayers
          })
        }

        alert(`Linked "${detectedName}" as nickname to ${rosterPlayerName}`)
        setLinkingPlayer(null)
        setSelectedRosterPlayer("")
      } else {
        alert("Failed to link player. Please try again.")
      }
    } catch (err) {
      console.error("Error linking player:", err)
      alert("Error linking player. Please try again.")
    }
  }

  const handleAddNewPlayer = async (
    resultId: number,
    playerIndex: number,
    name: string,
    memberStatus: string
  ) => {
    if (!data?.session?.guild_id || !name.trim()) return

    setIsAddingPlayer(true)

    try {
      // Add player to roster
      const success = await api.addPlayer(
        data.session.guild_id.toString(),
        name,
        memberStatus
      )

      if (success) {
        // Refresh roster list so new player appears in Link dropdown
        await refreshRosterPlayers()

        // Track as newly added player (for "New" badge)
        setNewlyAddedPlayers(prev => new Set(prev).add(name))

        // Update ALL results that have this player to mark as is_roster_member: true
        const updatePromises = results
          .map((result) => {
            const players = result.corrected_players || result.detected_players
            const hasPlayer = players.some(p => p.name.toLowerCase() === name.toLowerCase())

            if (hasPlayer) {
              const updatedPlayers = players.map(p =>
                p.name.toLowerCase() === name.toLowerCase()
                  ? { ...p, name: name, is_roster_member: true }
                  : p
              )

              return updateResultMutation.mutateAsync({
                resultId: result.id,
                status: result.review_status,
                corrected: updatedPlayers
              })
            }
            return null
          })
          .filter(Boolean)

        await Promise.all(updatePromises)

        alert(`Added "${name}" to roster as ${memberStatus}`)
        setAddingNewPlayer(null)
        setNewPlayerFormData({ name: "", memberStatus: "member" })
      } else {
        throw new Error("Failed to add player")
      }
    } catch (err) {
      console.error("Error adding player:", err)
      alert("Player already exists in roster. Try linking instead.")
    } finally {
      setIsAddingPlayer(false)
    }
  }

  const totalScore = (players: BulkPlayer[]) =>
    players.reduce((sum, p) => sum + p.score, 0)

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur">
        <div className="max-w-[1400px] mx-auto px-6 flex h-14 items-center justify-between">
          <div>
            <h1 className="font-bold">Bulk Scan Review</h1>
            <p className="text-xs text-muted-foreground">
              {session.total_images} images to review
            </p>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 text-sm">
              <Badge variant="success" className="gap-1">
                <CheckCircle2 className="h-3 w-3" />
                {approvedCount}
              </Badge>
              <Badge variant="secondary" className="gap-1">
                <Clock className="h-3 w-3" />
                {pendingCount}
              </Badge>
              <Badge variant="destructive" className="gap-1">
                <X className="h-3 w-3" />
                {rejectedCount}
              </Badge>
            </div>
            <Button
              onClick={handleConfirmAndSave}
              disabled={approvedCount === 0 || isSaving}
              className="gap-2"
            >
              {isSaving ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Save className="h-4 w-4" />
              )}
              Save {approvedCount} Wars
            </Button>
          </div>
        </div>
      </header>

      {/* Actions Bar */}
      <div className="border-b bg-muted/50">
        <div className="max-w-[1400px] mx-auto px-6 py-2 flex items-center gap-4">
          <Button variant="outline" size="sm" onClick={handleApproveAll}>
            <Check className="mr-2 h-4 w-4" />
            Approve All Pending
          </Button>
          <span className="text-sm text-muted-foreground">
            Review each war below. Click player names to edit or add to roster.
          </span>
        </div>
      </div>

      {/* Results Grid */}
      <div className="max-w-[1400px] mx-auto px-6 py-6">
        <div className="space-y-6">
          {results.map((result, index) => {
            const players = result.corrected_players || result.detected_players
            const isEditing = editingResult === result.id

            return (
              <Card
                key={result.id}
                className={`transition-all ${
                  result.review_status === "approved"
                    ? "border-green-500/50 bg-green-50/50 dark:bg-green-950/20"
                    : result.review_status === "rejected"
                    ? "border-red-500/50 bg-red-50/50 dark:bg-red-950/20"
                    : ""
                }`}
              >
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <CardTitle className="text-lg">
                        Table {index + 1}/{results.length}
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
                    <div className="flex items-center gap-2">
                      {!isEditing && (
                        <>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleEdit(result)}
                          >
                            <Edit2 className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-green-600 hover:text-green-700"
                            onClick={() => handleApprove(result.id)}
                          >
                            <Check className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-red-600 hover:text-red-700"
                            onClick={() => handleReject(result.id)}
                          >
                            <X className="h-4 w-4" />
                          </Button>
                        </>
                      )}
                    </div>
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
                    {/* Left: Image */}
                    <div className="w-full md:w-[600px] flex-shrink-0">
                      {result.image_url ? (
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

                    {/* Right: Players Column */}
                    <div className="flex-1 space-y-2">
                      {isEditing ? (
                        <>
                          {editedPlayers.map((player, idx) => (
                            <div key={idx} className="flex gap-2 items-center">
                              <Input
                                value={player.name}
                                onChange={(e) =>
                                  handlePlayerChange(idx, "name", e.target.value)
                                }
                                className="flex-1"
                                placeholder="Player name"
                              />
                              <Input
                                type="text"
                                inputMode="numeric"
                                value={player.score}
                                onChange={(e) => {
                                  const value = e.target.value
                                  if (value === '' || /^\d+$/.test(value)) {
                                    handlePlayerChange(idx, "score", value === '' ? 0 : parseInt(value))
                                  }
                                }}
                                className="w-24"
                                placeholder="Score"
                              />
                              <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => {
                                  const updated = editedPlayers.filter((_, i) => i !== idx)
                                  setEditedPlayers(updated)
                                }}
                                title="Remove player"
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            </div>
                          ))}

                          {/* Add Player Button */}
                          <Button
                            variant="outline"
                            className="w-full"
                            onClick={() => {
                              setEditedPlayers([...editedPlayers, { name: "", score: 0, is_roster_member: false }])
                            }}
                          >
                            <Plus className="h-4 w-4 mr-2" />
                            Add Player
                          </Button>

                          {/* Action Buttons */}
                          <div className="flex justify-end gap-2 pt-2">
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => {
                                setEditingResult(null)
                                setEditedPlayers([])
                              }}
                            >
                              Cancel
                            </Button>
                            <Button
                              size="sm"
                              onClick={() => handleSaveEdit(result.id)}
                            >
                              Save & Approve
                            </Button>
                          </div>
                        </>
                      ) : (
                        <>
                          {players.map((player, idx) => (
                            <div key={idx}>
                              <div
                                className={`flex justify-between items-center p-3 rounded-md ${
                                  player.is_roster_member
                                    ? "bg-muted/50"
                                    : "bg-yellow-100 dark:bg-yellow-900/30 border border-yellow-300"
                                }`}
                              >
                                <div className="flex items-center gap-2 flex-1">
                                  <span
                                    className={`${
                                      !player.is_roster_member
                                        ? "text-yellow-700 dark:text-yellow-400 font-medium"
                                        : ""
                                    }`}
                                  >
                                    {player.name}
                                  </span>
                                  {newlyAddedPlayers.has(player.name) && (
                                    <Badge variant="success" className="text-xs">
                                      New
                                    </Badge>
                                  )}
                                </div>
                                <span className="font-semibold mr-2">{player.score}</span>
                                {!player.is_roster_member && (
                                  <div className="flex gap-2">
                                    <Button
                                      variant="outline"
                                      size="sm"
                                      className="h-7 text-xs"
                                      onClick={() => setLinkingPlayer({ resultId: result.id, playerIndex: idx, playerName: player.name })}
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
                                        setNewPlayerFormData({ name: player.name, memberStatus: "member" })
                                      }}
                                    >
                                      <UserPlus className="h-3 w-3 mr-1" />
                                      Add as New
                                    </Button>
                                  </div>
                                )}
                              </div>
                              {linkingPlayer?.resultId === result.id && linkingPlayer?.playerIndex === idx && (
                                <div className="mt-2 p-3 bg-background border rounded-md">
                                  <label className="text-sm font-medium mb-2 block">
                                    Link "{player.name}" to roster player:
                                  </label>
                                  <div className="flex gap-2">
                                    <select
                                      className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm"
                                      value={selectedRosterPlayer}
                                      onChange={(e) => setSelectedRosterPlayer(e.target.value)}
                                    >
                                      <option value="">Select a player...</option>
                                      {rosterPlayers.map((rp) => (
                                        <option key={rp} value={rp}>
                                          {rp}
                                        </option>
                                      ))}
                                    </select>
                                    <Button
                                      size="sm"
                                      onClick={() => handleLinkPlayer(result.id, idx, player.name, selectedRosterPlayer)}
                                      disabled={!selectedRosterPlayer}
                                    >
                                      Link
                                    </Button>
                                    <Button
                                      variant="outline"
                                      size="sm"
                                      onClick={() => {
                                        setLinkingPlayer(null)
                                        setSelectedRosterPlayer("")
                                      }}
                                    >
                                      Cancel
                                    </Button>
                                  </div>
                                </div>
                              )}
                              {addingNewPlayer?.resultId === result.id && addingNewPlayer?.playerIndex === idx && (
                                <div className="mt-2 p-3 bg-background border rounded-md">
                                  <label className="text-sm font-medium mb-2 block">
                                    Add as New Player to Roster
                                  </label>
                                  <div className="space-y-2">
                                    <Input
                                      value={newPlayerFormData.name}
                                      onChange={(e) => setNewPlayerFormData({ ...newPlayerFormData, name: e.target.value })}
                                      placeholder="Player name"
                                      className="w-full"
                                    />
                                    <select
                                      className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm"
                                      value={newPlayerFormData.memberStatus}
                                      onChange={(e) => setNewPlayerFormData({ ...newPlayerFormData, memberStatus: e.target.value })}
                                    >
                                      <option value="member">Member</option>
                                      <option value="trial">Trial</option>
                                      <option value="ally">Ally</option>
                                      <option value="kicked">Kicked</option>
                                    </select>
                                    <div className="flex gap-2">
                                      <Button
                                        size="sm"
                                        onClick={() => handleAddNewPlayer(result.id, idx, newPlayerFormData.name, newPlayerFormData.memberStatus)}
                                        disabled={!newPlayerFormData.name.trim() || isAddingPlayer}
                                      >
                                        {isAddingPlayer && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
                                        Add Player
                                      </Button>
                                      <Button
                                        variant="outline"
                                        size="sm"
                                        onClick={() => {
                                          setAddingNewPlayer(null)
                                          setNewPlayerFormData({ name: "", memberStatus: "member" })
                                        }}
                                        disabled={isAddingPlayer}
                                      >
                                        Cancel
                                      </Button>
                                    </div>
                                  </div>
                                </div>
                              )}
                            </div>
                          ))}
                          {players.some((p) => !p.is_roster_member) && (
                            <p className="text-xs text-yellow-600 dark:text-yellow-500 mt-2">
                              Players highlighted in yellow are not in your roster. Click "Link" to add as nickname to an existing player.
                            </p>
                          )}
                        </>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      </div>
    </div>
  )
}
