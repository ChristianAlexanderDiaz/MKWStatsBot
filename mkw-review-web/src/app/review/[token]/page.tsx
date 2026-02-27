"use client"

/**
 * BulkReviewPage - thin shell for the bulk OCR scan review flow.
 *
 * All state, mutations, and event handlers live in useBulkReview.
 * This component is responsible only for layout and routing between the
 * loading / error / ready states.
 */

import { useParams, useRouter } from "next/navigation"
import { AlertCircle } from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { LoadingSpinner } from "@/components/shared/LoadingSpinner"
import { ReviewHeader } from "@/components/review/ReviewHeader"
import { WarResultCard } from "@/components/review/WarResultCard"
import { FailureCard } from "@/components/review/FailureCard"
import { useBulkReview } from "@/hooks/useBulkReview"

export default function BulkReviewPage() {
  const params = useParams()
  const router = useRouter()
  const token = params.token as string

  const {
    data,
    isLoading,
    error,
    approvedCount,
    pendingCount,
    rejectedCount,
    editingResult,
    setEditingResult,
    editedPlayers,
    setEditedPlayers,
    isSaving,
    linkingPlayer,
    setLinkingPlayer,
    linkSearchQuery,
    setLinkSearchQuery,
    addingNewPlayer,
    setAddingNewPlayer,
    newPlayerFormData,
    setNewPlayerFormData,
    newlyAddedPlayers,
    stagedPlayers,
    showStagedMenu,
    setShowStagedMenu,
    editingFailure,
    failureEditedPlayers,
    allAvailablePlayers,
    totalScore,
    convertFailureMutation,
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
  } = useBulkReview(token, router)

  if (isLoading) {
    return <LoadingSpinner label="Loading review session..." />
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

  const { session, results = [], failures = [] } = data

  return (
    <div className="min-h-screen bg-background">
      <ReviewHeader
        session={session}
        approvedCount={approvedCount}
        pendingCount={pendingCount}
        rejectedCount={rejectedCount}
        stagedPlayers={stagedPlayers}
        showStagedMenu={showStagedMenu}
        setShowStagedMenu={setShowStagedMenu}
        onRemoveStagedPlayer={handleRemoveStagedPlayer}
        isSaving={isSaving}
        onConfirmAndSave={handleConfirmAndSave}
        onApproveAll={handleApproveAll}
      />

      <div className="max-w-[1400px] mx-auto px-6 py-6">
        {/* War result cards */}
        <div className="space-y-6">
          {results.map((result, index) => (
            <WarResultCard
              key={result.id}
              result={result}
              index={index}
              totalResults={results.length}
              editingResult={editingResult}
              editedPlayers={editedPlayers}
              setEditedPlayers={setEditedPlayers}
              setEditingResult={setEditingResult}
              linkingPlayer={linkingPlayer}
              setLinkingPlayer={setLinkingPlayer}
              linkSearchQuery={linkSearchQuery}
              setLinkSearchQuery={setLinkSearchQuery}
              addingNewPlayer={addingNewPlayer}
              setAddingNewPlayer={setAddingNewPlayer}
              newPlayerFormData={newPlayerFormData}
              setNewPlayerFormData={setNewPlayerFormData}
              newlyAddedPlayers={newlyAddedPlayers}
              allAvailablePlayers={allAvailablePlayers}
              totalScore={totalScore}
              onApprove={handleApprove}
              onReject={handleReject}
              onEdit={handleEdit}
              onSaveEdit={handleSaveEdit}
              onPlayerChange={handlePlayerChange}
              onLinkPlayer={handleLinkPlayer}
              onAddNewPlayer={handleAddNewPlayer}
            />
          ))}
        </div>

        {/* Failed images section */}
        {failures.length > 0 && (
          <div className="mt-12">
            <h2 className="text-xl font-bold mb-4 text-muted-foreground">
              Failed Images ({failures.length})
            </h2>
            <div className="space-y-6">
              {failures.map((failure) => (
                <FailureCard
                  key={failure.id}
                  failure={failure}
                  editingFailure={editingFailure}
                  failureEditedPlayers={failureEditedPlayers}
                  onEditFailure={handleEditFailure}
                  onCancelEditFailure={handleCancelEditFailure}
                  onPlayerChange={handleFailurePlayerChange}
                  onAddPlayer={handleAddFailurePlayer}
                  onRemovePlayer={handleRemoveFailurePlayer}
                  onSaveFailure={handleSaveFailure}
                  pendingStatus={
                    convertFailureMutation.isPending
                      ? convertFailureMutation.variables?.status === "pending" ? "pending"
                        : convertFailureMutation.variables?.status === "approved" ? "approved"
                        : null
                      : null
                  }
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
