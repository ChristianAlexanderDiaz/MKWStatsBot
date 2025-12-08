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
  Loader2
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

  const { data, isLoading, error } = useQuery({
    queryKey: ["bulk-review", token],
    queryFn: () => api.getBulkResults(token),
    refetchInterval: false,
  })

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

  const totalScore = (players: BulkPlayer[]) =>
    players.reduce((sum, p) => sum + p.score, 0)

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur">
        <div className="container flex h-14 items-center justify-between">
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
        <div className="container py-2 flex items-center gap-4">
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
      <div className="container py-6">
        <div className="grid gap-4">
          {results.map((result) => {
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
                        {result.image_filename || `War ${result.id}`}
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
                    {result.message_timestamp
                      ? new Date(result.message_timestamp).toLocaleString()
                      : "Unknown time"}{" "}
                    | {players.length} players | Team Score: {totalScore(players)}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {isEditing ? (
                    <div className="space-y-4">
                      <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                        {editedPlayers.map((player, idx) => (
                          <div
                            key={idx}
                            className="flex items-center gap-2 p-2 rounded border bg-background"
                          >
                            <Input
                              value={player.name}
                              onChange={(e) =>
                                handlePlayerChange(idx, "name", e.target.value)
                              }
                              className="h-8 text-sm"
                            />
                            <Input
                              type="number"
                              value={player.score}
                              onChange={(e) =>
                                handlePlayerChange(idx, "score", parseInt(e.target.value) || 0)
                              }
                              className="h-8 w-20 text-sm"
                            />
                          </div>
                        ))}
                      </div>
                      <div className="flex justify-end gap-2">
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
                    </div>
                  ) : (
                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
                      {players.map((player, idx) => (
                        <div
                          key={idx}
                          className={`flex items-center justify-between p-2 rounded text-sm ${
                            player.is_roster_member
                              ? "bg-muted"
                              : "bg-yellow-100 dark:bg-yellow-900/30 border border-yellow-300"
                          }`}
                        >
                          <span
                            className={`truncate ${
                              !player.is_roster_member ? "text-yellow-700 dark:text-yellow-400" : ""
                            }`}
                          >
                            {player.name}
                          </span>
                          <span className="font-medium ml-2">{player.score}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  {!isEditing && players.some((p) => !p.is_roster_member) && (
                    <p className="text-xs text-yellow-600 mt-2">
                      Players highlighted in yellow are not in your roster
                    </p>
                  )}
                </CardContent>
              </Card>
            )
          })}
        </div>
      </div>
    </div>
  )
}
