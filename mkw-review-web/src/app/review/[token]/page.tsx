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
  const [newlyAddedPlayers, setNewlyAddedPlayers] = useState<Set<string>>(new Set())
  const [stagedPlayers, setStagedPlayers] = useState<Array<{ name: string; memberStatus: string }>>([])
  const [editingFailure, setEditingFailure] = useState<number | null>(null)
  const [failureEditedPlayers, setFailureEditedPlayers] = useState<BulkPlayer[]>([])
  const [linkSearchQuery, setLinkSearchQuery] = useState("")

  const { data, isLoading, error } = useQuery({
    queryKey: ["bulk-review", token],
    queryFn: () => api.getBulkResults(token),
    refetchInterval: false,
  })

  // Fetch roster players for linking functionality
  const refreshRosterPlayers = async () => {
    if (data?.session?.guild_id) {
      try {
        console.log('Fetching all players for guild_id:', data.session.guild_id)
        const result = await api.getAllPlayers(data.session.guild_id.toString())
        console.log('All players API response:', result)
        const playerNames = result.players.map((p: any) => p.name)
        console.log('All player names:', playerNames)
        setRosterPlayers(playerNames)
      } catch (err) {
        console.error("Failed to fetch players:", err)
      }
    } else {
      console.warn('Cannot fetch players: guild_id not available', data?.session)
    }
  }

  useEffect(() => {
    refreshRosterPlayers()
  }, [data?.session?.guild_id])

  // Check if a player is "known" (either in roster or staged)
  const isKnownPlayer = (playerName: string) => {
    const inRoster = rosterPlayers.some(p => p.toLowerCase() === playerName.toLowerCase())
    const inStaged = stagedPlayers.some(p => p.name.toLowerCase() === playerName.toLowerCase())
    return inRoster || inStaged
  }

  // Combine roster + staged for Link dropdown
  const allAvailablePlayers = [
    ...rosterPlayers,
    ...stagedPlayers.map(p => p.name)
  ]

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

  const convertFailureMutation = useMutation({
    mutationFn: async ({ failureId, players, status }: {
      failureId: number
      players: BulkPlayer[]
      status: 'pending' | 'approved' | 'rejected'
    }) => {
      return api.convertFailureToResult(token, failureId, players, status)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["bulk-review", token] })
      setEditingFailure(null)
      setFailureEditedPlayers([])
    }
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

  const { session, results, failures = [] } = data
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
    const players = result.corrected_players || result.detected_players
    // Ensure races_played has a default value (war's race_count)
    const playersWithDefaults = players.map(p => ({
      ...p,
      races_played: p.races_played || result.race_count || 12
    }))
    setEditedPlayers(playersWithDefaults)
  }

  const handleSaveEdit = (resultId: number) => {
    // Find current status and preserve it
    const result = results.find(r => r.id === resultId)
    const currentStatus = result?.review_status || "pending"

    updateResultMutation.mutate({
      resultId,
      status: currentStatus,
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

  // Failure editing handlers
  const handleEditFailure = (failureId: number) => {
    setEditingFailure(failureId)
    setFailureEditedPlayers([{ name: "", score: 0, is_roster_member: false }])
  }

  const handleCancelEditFailure = () => {
    setEditingFailure(null)
    setFailureEditedPlayers([])
  }

  const handleFailurePlayerChange = (index: number, field: keyof BulkPlayer, value: string | number | boolean) => {
    const updated = [...failureEditedPlayers]
    updated[index] = { ...updated[index], [field]: value }
    setFailureEditedPlayers(updated)
  }

  const handleAddFailurePlayer = () => {
    setFailureEditedPlayers([...failureEditedPlayers, { name: "", score: 0, is_roster_member: false }])
  }

  const handleRemoveFailurePlayer = (index: number) => {
    setFailureEditedPlayers(failureEditedPlayers.filter((_, i) => i !== index))
  }

  const handleSaveFailure = (failureId: number, status: 'pending' | 'approved' | 'rejected') => {
    const validPlayers = failureEditedPlayers.filter(p => p.name.trim() !== '')
    if (validPlayers.length === 0) {
      alert('Please add at least one player')
      return
    }
    convertFailureMutation.mutate({ failureId, players: validPlayers, status })
  }

  const handleConfirmAndSave = async () => {
    if (!data?.session?.guild_id) return

    setIsSaving(true)

    try {
      // First, create all staged players
      if (stagedPlayers.length > 0) {
        for (const player of stagedPlayers) {
          await api.addPlayer(
            data.session.guild_id.toString(),
            player.name,
            player.memberStatus
          )
        }
      }

      // Then confirm the session (creates wars)
      await confirmMutation.mutateAsync()
    } catch (err) {
      console.error("Error confirming session:", err)
      alert("Error saving wars. Please try again.")
    } finally {
      setIsSaving(false)
    }
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

  const handleAddNewPlayer = (
    resultId: number,
    playerIndex: number,
    name: string,
    memberStatus: string
  ) => {
    if (!name.trim()) return

    // Check if already in roster OR already staged
    const isInRoster = rosterPlayers.some(p => p.toLowerCase() === name.toLowerCase())
    const isStaged = stagedPlayers.some(p => p.name.toLowerCase() === name.toLowerCase())

    if (isInRoster || isStaged) {
      alert("Player already exists. Try linking instead.")
      return
    }

    // Stage the player locally (NO API call - will be created on confirm)
    setStagedPlayers(prev => [...prev, { name, memberStatus }])
    setNewlyAddedPlayers(prev => new Set(prev).add(name))

    // Close the form
    setAddingNewPlayer(null)
    setNewPlayerFormData({ name: "", memberStatus: "member" })
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
              {stagedPlayers.length > 0 && (
                <Badge variant="outline" className="gap-1 border-blue-500 text-blue-600">
                  <UserPlus className="h-3 w-3" />
                  {stagedPlayers.length} new
                </Badge>
              )}
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
                              <Input
                                type="text"
                                inputMode="numeric"
                                value={player.races_played}
                                onChange={(e) => {
                                  const value = e.target.value
                                  if (value === '' || /^\d+$/.test(value)) {
                                    handlePlayerChange(idx, "races_played", value === '' ? 0 : parseInt(value))
                                  }
                                }}
                                className="w-16"
                                placeholder="Races"
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
                              Save
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
                                <div className="flex items-center gap-2 mr-2">
                                  <span className="font-semibold">{player.score}</span>
                                  <span className="text-xs text-muted-foreground">
                                    ({player.races_played || result.race_count || 12}/{result.race_count || 12} races)
                                  </span>
                                </div>
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
                                        setNewPlayerFormData({ name: player.name, memberStatus: "member" })
                                        setLinkingPlayer(null)
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
                                      {allAvailablePlayers
                                        .filter(name =>
                                          linkSearchQuery === "" ||
                                          name.toLowerCase().includes(linkSearchQuery.toLowerCase())
                                        )
                                        .map((name) => (
                                          <button
                                            key={name}
                                            className="w-full px-3 py-2 text-left text-sm hover:bg-muted border-b last:border-b-0"
                                            onClick={() => handleLinkPlayer(result.id, idx, player.name, name)}
                                          >
                                            {name}
                                          </button>
                                        ))}
                                      {allAvailablePlayers.filter(name =>
                                        linkSearchQuery === "" ||
                                        name.toLowerCase().includes(linkSearchQuery.toLowerCase())
                                      ).length === 0 && (
                                        <div className="px-3 py-2 text-sm text-muted-foreground">
                                          No players found
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
                                        disabled={!newPlayerFormData.name.trim()}
                                      >
                                        Stage Player
                                      </Button>
                                      <Button
                                        variant="outline"
                                        size="sm"
                                        onClick={() => {
                                          setAddingNewPlayer(null)
                                          setNewPlayerFormData({ name: "", memberStatus: "member" })
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
                          {players.some((p) => !p.is_roster_member) && (
                            <p className="text-xs text-yellow-600 dark:text-yellow-500 mt-2">
                              Yellow = not in roster. Use "Link" to connect to existing player, or "Add as New" to create new.
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

        {/* Failed Images Section */}
        {failures && failures.length > 0 && (
          <div className="mt-12">
            <h2 className="text-xl font-bold mb-4 text-muted-foreground">
              Failed Images ({failures.length})
            </h2>
            <div className="space-y-6">
              {failures.map((failure) => {
                const isEditingThis = editingFailure === failure.id
                return (
                  <Card key={failure.id} className="border-red-500/30 bg-red-50/30 dark:bg-red-950/10">
                    <CardHeader className="pb-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <CardTitle className="text-lg text-red-600 dark:text-red-400">
                            Failed to Process
                          </CardTitle>
                          <Badge variant="destructive">Error</Badge>
                        </div>
                        {!isEditingThis && (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleEditFailure(failure.id)}
                          >
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
                        {/* Image */}
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

                        {/* Edit Mode or Error Display */}
                        <div className="flex-1">
                          {isEditingThis ? (
                            <div className="space-y-3">
                              <p className="text-sm text-muted-foreground mb-2">
                                Manually enter the players from this image:
                              </p>
                              {failureEditedPlayers.map((player, index) => (
                                <div key={index} className="flex items-center gap-2">
                                  <Input
                                    placeholder="Player name"
                                    value={player.name}
                                    onChange={(e) => handleFailurePlayerChange(index, "name", e.target.value)}
                                    className="flex-1"
                                  />
                                  <Input
                                    type="number"
                                    placeholder="Score"
                                    value={player.score || ""}
                                    onChange={(e) => handleFailurePlayerChange(index, "score", parseInt(e.target.value) || 0)}
                                    className="w-20"
                                  />
                                  <Input
                                    type="text"
                                    inputMode="numeric"
                                    placeholder="Races"
                                    value={player.races_played}
                                    onChange={(e) => {
                                      const value = e.target.value
                                      if (value === '' || /^\d+$/.test(value)) {
                                        handleFailurePlayerChange(index, "races_played", value === '' ? 0 : parseInt(value))
                                      }
                                    }}
                                    className="w-16"
                                  />
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    onClick={() => handleRemoveFailurePlayer(index)}
                                    disabled={failureEditedPlayers.length <= 1}
                                  >
                                    <Trash2 className="h-4 w-4 text-destructive" />
                                  </Button>
                                </div>
                              ))}
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={handleAddFailurePlayer}
                                className="w-full"
                              >
                                <Plus className="h-4 w-4 mr-1" />
                                Add Player
                              </Button>
                              <div className="flex gap-2 mt-4">
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={handleCancelEditFailure}
                                >
                                  Cancel
                                </Button>
                                <Button
                                  size="sm"
                                  onClick={() => handleSaveFailure(failure.id, "pending")}
                                  disabled={convertFailureMutation.isPending}
                                >
                                  {convertFailureMutation.isPending ? (
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
                                  onClick={() => handleSaveFailure(failure.id, "approved")}
                                  disabled={convertFailureMutation.isPending}
                                >
                                  <Check className="h-4 w-4 mr-1" />
                                  Save & Approve
                                </Button>
                              </div>
                            </div>
                          ) : (
                            <>
                              <div className="border border-dashed border-red-300 rounded-md p-6 bg-background">
                                <div className="flex items-start gap-3">
                                  <AlertCircle className="h-5 w-5 text-red-500 mt-0.5" />
                                  <div>
                                    <p className="font-medium text-red-600 mb-2">
                                      Processing Error
                                    </p>
                                    <p className="text-sm text-muted-foreground">
                                      {failure.error_message}
                                    </p>
                                  </div>
                                </div>
                              </div>
                              <p className="text-xs text-muted-foreground mt-4 italic">
                                Click "Edit Manually" to add players for this image.
                              </p>
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
        )}
      </div>
    </div>
  )
}
