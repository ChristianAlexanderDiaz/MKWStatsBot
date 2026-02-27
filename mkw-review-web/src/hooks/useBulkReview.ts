"use client"

/**
 * useBulkReview - custom hook for the bulk scan review page.
 *
 * Extracts all state, mutations, and event handlers out of BulkReviewPage so
 * the page component stays a thin layout/render shell.  Every handler that
 * was previously an inline function in page.tsx lives here instead.
 */

import { useState, useEffect, useCallback } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { AppRouterInstance } from "next/dist/shared/lib/app-router-context.shared-runtime"
import { api } from "@/lib/api"
import type { BulkResult, BulkPlayer, StagedPlayer } from "@/lib/types"

export function useBulkReview(token: string, router: AppRouterInstance) {
  const queryClient = useQueryClient()

  // ---- Edit state (for modifying a result's player list inline) ----
  const [editingResult, setEditingResult] = useState<number | null>(null)
  const [editedPlayers, setEditedPlayers] = useState<BulkPlayer[]>([])

  // ---- Session-level UI state ----
  const [isSaving, setIsSaving] = useState(false)
  const [showStagedMenu, setShowStagedMenu] = useState(false)

  // ---- Link-player flow (match an unknown OCR name to an existing roster player) ----
  const [linkingPlayer, setLinkingPlayer] = useState<{
    resultId: number
    playerIndex: number
    playerName: string
  } | null>(null)
  const [linkSearchQuery, setLinkSearchQuery] = useState("")

  // ---- Add-new-player flow (stage a brand-new roster member before confirming) ----
  const [addingNewPlayer, setAddingNewPlayer] = useState<{
    resultId: number
    playerIndex: number
    playerName: string
  } | null>(null)
  const [newPlayerFormData, setNewPlayerFormData] = useState<{
    name: string
    memberStatus: string
  }>({ name: "", memberStatus: "ally" })

  // ---- Roster / staged players ----
  // rosterPlayers: fetched from the API after session loads
  // stagedPlayers: locally queued new players (created on confirm, not before)
  // newlyAddedPlayers: tracks which names were just staged so we can show a "New" badge
  const [rosterPlayers, setRosterPlayers] = useState<string[]>([])
  const [stagedPlayers, setStagedPlayers] = useState<StagedPlayer[]>([])
  const [newlyAddedPlayers, setNewlyAddedPlayers] = useState<Set<string>>(new Set())

  // ---- Failure-image editing (manually entering players for an image OCR couldn't parse) ----
  const [editingFailure, setEditingFailure] = useState<number | null>(null)
  const [failureEditedPlayers, setFailureEditedPlayers] = useState<BulkPlayer[]>([])

  // ---- Inline notifications (replaces browser alert() calls) ----
  const [notification, setNotification] = useState<{
    type: "success" | "error" | "warning"
    message: string
  } | null>(null)
  const notify = (type: "success" | "error" | "warning", message: string) =>
    setNotification({ type, message })
  const clearNotification = () => setNotification(null)

  // Close the staged-players dropdown on Escape
  useEffect(() => {
    if (!showStagedMenu) return
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") setShowStagedMenu(false)
    }
    window.addEventListener("keydown", handleEscape)
    return () => window.removeEventListener("keydown", handleEscape)
  }, [showStagedMenu])

  // ---- Data fetching ----

  const { data, isLoading, error } = useQuery({
    queryKey: ["bulk-review", token],
    queryFn: () => api.getBulkResults(token),
    refetchInterval: false,
  })

  // Fetch all roster players once we know the guild_id from the session
  const refreshRosterPlayers = useCallback(async () => {
    if (!data?.session?.guild_id) return
    try {
      const result = await api.getAllPlayers(data.session.guild_id)
      setRosterPlayers(result.players.map((p) => p.name))
    } catch (err) {
      console.error("Failed to fetch players:", err)
    }
  }, [data?.session?.guild_id])

  useEffect(() => {
    refreshRosterPlayers()
  }, [refreshRosterPlayers])

  // ---- Derived values ----

  // Combined list used by the Link dropdown (roster + staged-but-not-yet-saved)
  const allAvailablePlayers = [
    ...rosterPlayers,
    ...stagedPlayers.map((p) => p.name),
  ]

  const totalScore = (players: BulkPlayer[]) =>
    players.reduce((sum, p) => sum + p.score, 0)

  const results = data?.results ?? []
  const approvedCount = results.filter((r) => r.review_status === "approved").length
  const pendingCount = results.filter((r) => r.review_status === "pending").length
  const rejectedCount = results.filter((r) => r.review_status === "rejected").length

  // ---- Mutations ----

  // Update a single result's status and/or corrected player list
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
    onError: (err) => {
      console.error("Failed to update result:", err)
      queryClient.invalidateQueries({ queryKey: ["bulk-review", token] })
    },
  })

  // Finalise the session: creates wars from all approved results
  const confirmMutation = useMutation({
    mutationFn: () => api.confirmBulkSession(token),
    onSuccess: (result) => {
      if (result) {
        router.push(`/dashboard?wars_created=${result.wars_created}`)
      }
    },
  })

  // Convert a failed OCR image into a manually-entered result
  const convertFailureMutation = useMutation({
    mutationFn: async ({
      failureId,
      players,
      status,
    }: {
      failureId: number
      players: BulkPlayer[]
      status: "pending" | "approved" | "rejected"
    }) => api.convertFailureToResult(token, failureId, players, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["bulk-review", token] })
      setEditingFailure(null)
      setFailureEditedPlayers([])
    },
    onError: (err) => {
      console.error("Failed to convert failure:", err)
      queryClient.invalidateQueries({ queryKey: ["bulk-review", token] })
    },
  })

  // ---- Result handlers ----

  const handleApprove = (resultId: number) => {
    // If we're mid-edit on this result, flush the edits as part of the approval
    const corrected = editingResult === resultId ? editedPlayers : undefined
    updateResultMutation.mutate({ resultId, status: "approved", corrected })
    if (editingResult === resultId) {
      setEditingResult(null)
      setEditedPlayers([])
    }
  }

  const handleReject = (resultId: number) => {
    const corrected = editingResult === resultId ? editedPlayers : undefined
    updateResultMutation.mutate({ resultId, status: "rejected", corrected })
    if (editingResult === resultId) {
      setEditingResult(null)
      setEditedPlayers([])
    }
  }

  const handleEdit = (result: BulkResult) => {
    setEditingResult(result.id)
    const players = result.corrected_players || result.detected_players
    // Pre-fill races_played so the field is never blank in the edit form
    setEditedPlayers(
      players.map((p) => ({
        ...p,
        races_played: p.races_played || result.race_count || 12,
      }))
    )
  }

  const handleSaveEdit = (resultId: number) => {
    // Preserve the existing review status when saving edits
    const result = results.find((r) => r.id === resultId)
    const currentStatus = result?.review_status || "pending"
    updateResultMutation.mutate({ resultId, status: currentStatus, corrected: editedPlayers })
    setEditingResult(null)
    setEditedPlayers([])
  }

  const handlePlayerChange = (
    index: number,
    field: keyof BulkPlayer,
    value: string | number
  ) => {
    const updated = [...editedPlayers]
    updated[index] = { ...updated[index], [field]: value }
    setEditedPlayers(updated)
  }

  // Approve every pending result at once
  const handleApproveAll = () => {
    const pending = results.filter((r) => r.review_status === "pending")
    const mutations = pending.map((r) => {
      const corrected = editingResult === r.id ? editedPlayers : undefined
      return updateResultMutation.mutateAsync({ resultId: r.id, status: "approved", corrected })
    })
    Promise.allSettled(mutations).then(() => {
      if (editingResult !== null) {
        setEditingResult(null)
        setEditedPlayers([])
      }
    })
  }

  // ---- Failure-image handlers ----

  const handleEditFailure = (failureId: number) => {
    setEditingFailure(failureId)
    // Start with one blank player row
    setFailureEditedPlayers([{ name: "", score: 0, is_roster_member: false, races_played: 12 }])
  }

  const handleCancelEditFailure = () => {
    setEditingFailure(null)
    setFailureEditedPlayers([])
  }

  const handleFailurePlayerChange = (
    index: number,
    field: keyof BulkPlayer,
    value: string | number | boolean
  ) => {
    const updated = [...failureEditedPlayers]
    updated[index] = { ...updated[index], [field]: value }
    setFailureEditedPlayers(updated)
  }

  const handleAddFailurePlayer = () => {
    setFailureEditedPlayers([
      ...failureEditedPlayers,
      { name: "", score: 0, is_roster_member: false, races_played: 12 },
    ])
  }

  const handleRemoveFailurePlayer = (index: number) => {
    setFailureEditedPlayers(failureEditedPlayers.filter((_, i) => i !== index))
  }

  const handleSaveFailure = (
    failureId: number,
    status: "pending" | "approved" | "rejected"
  ) => {
    const validPlayers = failureEditedPlayers.filter((p) => p.name.trim() !== "")
    if (validPlayers.length === 0 && status !== "rejected") {
      notify("error", "Please add at least one player")
      return
    }
    convertFailureMutation.mutate({ failureId, players: validPlayers, status })
  }

  // ---- Session confirm ----

  const handleConfirmAndSave = async () => {
    if (!data?.session?.guild_id) return
    setIsSaving(true)
    try {
      // Create all staged players first (they were queued locally, not yet in DB)
      const failedPlayers: string[] = []
      for (const player of stagedPlayers) {
        try {
          await api.addPlayer(data.session.guild_id, player.name, player.memberStatus)
        } catch (err) {
          console.error(`Failed to add staged player ${player.name}:`, err)
          failedPlayers.push(player.name)
        }
      }
      if (failedPlayers.length > 0) {
        notify("error", `Failed to add some players: ${failedPlayers.join(", ")}. Please retry.`)
        return
      }
      // Then finalise the session (creates wars from approved results)
      await confirmMutation.mutateAsync()
    } catch (err) {
      console.error("Error confirming session:", err)
      notify("error", "Error saving wars. Please try again.")
    } finally {
      setIsSaving(false)
    }
  }

  // ---- Link-player handler ----

  // Links a detected (unknown) name to an existing roster player by adding a nickname
  const handleLinkPlayer = async (
    resultId: number,
    playerIndex: number,
    detectedName: string,
    rosterPlayerName: string
  ) => {
    if (!data?.session?.guild_id || !rosterPlayerName) return
    try {
      const isStagedPlayer = stagedPlayers.some(
        (p) => p.name.toLowerCase() === rosterPlayerName.toLowerCase()
      )
      let success = true
      // Only call the addNickname API for already-saved roster players
      if (!isStagedPlayer) {
        success = await api.addNickname(
          data.session.guild_id,
          rosterPlayerName,
          detectedName
        )
      }
      if (success) {
        const result = results.find((r) => r.id === resultId)
        if (result) {
          const players = result.corrected_players || result.detected_players
          const updatedPlayers = players.map((p, idx) =>
            idx === playerIndex
              ? { ...p, name: rosterPlayerName, is_roster_member: true }
              : p
          )
          updateResultMutation.mutate({
            resultId,
            status: result.review_status,
            corrected: updatedPlayers,
          })
        }
        notify(
          "success",
          isStagedPlayer
            ? `Linked "${detectedName}" to staged player ${rosterPlayerName}`
            : `Linked "${detectedName}" as nickname to ${rosterPlayerName}`
        )
        setLinkingPlayer(null)
        setLinkSearchQuery("")
      } else {
        notify("error", "Failed to link player. Please try again.")
      }
    } catch (err) {
      console.error("Error linking player:", err)
      notify("error", "Error linking player. Please try again.")
    }
  }

  // ---- Add-new-player handler ----

  // Stages a brand-new player locally; they are created in the DB on session confirm
  const handleAddNewPlayer = (
    resultId: number,
    playerIndex: number,
    name: string,
    memberStatus: string
  ) => {
    if (!name.trim()) return
    const isInRoster = rosterPlayers.some((p) => p.toLowerCase() === name.toLowerCase())
    const isStaged = stagedPlayers.some((p) => p.name.toLowerCase() === name.toLowerCase())
    if (isInRoster || isStaged) {
      notify("warning", "Player already exists. Try linking instead.")
      return
    }
    setStagedPlayers((prev) => [...prev, { name, memberStatus }])
    setNewlyAddedPlayers((prev) => new Set(prev).add(name))
    setAddingNewPlayer(null)
    setNewPlayerFormData({ name: "", memberStatus: "ally" })
  }

  // ---- Staged-player removal ----

  // Removes a staged player and reverts their is_roster_member flag in any results that
  // reference them, with optimistic updates and rollback on error
  const handleRemoveStagedPlayer = async (playerToRemove: string) => {
    const prevStagedPlayers = [...stagedPlayers]
    const prevNewlyAddedPlayers = new Set(newlyAddedPlayers)
    try {
      setStagedPlayers((prev) => prev.filter((p) => p.name !== playerToRemove))
      setNewlyAddedPlayers((prev) => {
        const updated = new Set(prev)
        updated.delete(playerToRemove)
        return updated
      })
      // Un-mark this player as a roster member in every result that references them
      for (const result of results) {
        const players = result.corrected_players || result.detected_players
        const hasThisPlayer = players.some(
          (p) => p.name.toLowerCase() === playerToRemove.toLowerCase()
        )
        if (hasThisPlayer) {
          const updatedPlayers = players.map((p) =>
            p.name.toLowerCase() === playerToRemove.toLowerCase()
              ? { ...p, is_roster_member: false }
              : p
          )
          await updateResultMutation.mutateAsync({
            resultId: result.id,
            status: result.review_status,
            corrected: updatedPlayers,
          })
        }
      }
    } catch (error) {
      console.error("Failed to remove staged player:", error)
      setStagedPlayers(prevStagedPlayers)
      setNewlyAddedPlayers(prevNewlyAddedPlayers)
      notify(
        "error",
        `Failed to remove staged player: ${error instanceof Error ? error.message : "Unknown error"}`
      )
    }
  }

  return {
    // Query state
    data,
    isLoading,
    error,
    // Notification state
    notification,
    clearNotification,
    // Status counts
    approvedCount,
    pendingCount,
    rejectedCount,
    // Edit state
    editingResult,
    setEditingResult,
    editedPlayers,
    setEditedPlayers,
    isSaving,
    // Link state
    linkingPlayer,
    setLinkingPlayer,
    linkSearchQuery,
    setLinkSearchQuery,
    rosterPlayers,
    // Add-new-player state
    addingNewPlayer,
    setAddingNewPlayer,
    newPlayerFormData,
    setNewPlayerFormData,
    newlyAddedPlayers,
    // Staged players
    stagedPlayers,
    setStagedPlayers,
    showStagedMenu,
    setShowStagedMenu,
    // Failure editing state
    editingFailure,
    failureEditedPlayers,
    // Derived
    allAvailablePlayers,
    totalScore,
    // Mutations (exposed for isPending checks in child components)
    updateResultMutation,
    convertFailureMutation,
    // Handlers
    handleApprove,
    handleReject,
    handleEdit,
    handleSaveEdit,
    handlePlayerChange,
    handleApproveAll,
    handleEditFailure,
    handleCancelEditFailure,
    handleFailurePlayerChange,
    handleAddFailurePlayer,
    handleRemoveFailurePlayer,
    handleSaveFailure,
    handleConfirmAndSave,
    handleLinkPlayer,
    handleAddNewPlayer,
    handleRemoveStagedPlayer,
  }
}
