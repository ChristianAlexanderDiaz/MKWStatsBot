"use client"

import { useAuth } from "@/lib/auth"
import { api } from "@/lib/api"
import { useQuery } from "@tanstack/react-query"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { useState } from "react"
import { ChevronLeft, ChevronRight, TrendingUp, TrendingDown } from "lucide-react"

export default function WarsPage() {
  const { selectedGuild } = useAuth()
  const [page, setPage] = useState(1)
  const limit = 20

  const { data, isLoading } = useQuery({
    queryKey: ["wars", selectedGuild?.id, page],
    queryFn: () => api.getWars(selectedGuild!.id, page, limit),
    enabled: !!selectedGuild,
  })

  if (!selectedGuild) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-muted-foreground">Select a guild to view wars</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">War History</h1>
        <p className="text-muted-foreground">
          {data?.total || 0} wars recorded for {selectedGuild.name}
        </p>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
        </div>
      ) : (
        <>
          <div className="grid gap-4">
            {data?.wars.map((war) => {
              const scannedCount = war.players.length
              const totalPlayers = 6 // Standard MKW war team size
              return (
                <Card key={war.id}>
                  <CardContent className="p-4">
                    <div className="flex items-start justify-between">
                      <div>
                        <div className="flex items-center gap-2 mb-2">
                          <h3 className="font-medium">War #{war.id}</h3>
                          <Badge variant="outline">
                            {war.race_count} races
                          </Badge>
                          <Badge
                            variant={scannedCount === totalPlayers ? "success" : "secondary"}
                            className="gap-1"
                          >
                            Players: {scannedCount}/{totalPlayers}
                          </Badge>
                          <Badge
                            variant={war.team_differential >= 0 ? "success" : "destructive"}
                            className="gap-1"
                          >
                            {war.team_differential >= 0 ? (
                              <TrendingUp className="h-3 w-3" />
                            ) : (
                              <TrendingDown className="h-3 w-3" />
                            )}
                            {war.team_differential >= 0 ? "+" : ""}
                            {war.team_differential}
                          </Badge>
                        </div>
                      <p className="text-sm text-muted-foreground mb-3">
                        {new Date(war.created_at).toLocaleDateString()} |{" "}
                        Team Score: {war.team_score}
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {war.players.map((player, idx) => (
                          <div
                            key={idx}
                            className="flex items-center gap-1 px-2 py-1 rounded bg-muted text-sm"
                          >
                            <span>{player.name}</span>
                            <span className="font-medium text-muted-foreground">
                              {player.score}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
              )
            })}
          </div>

          {/* Pagination */}
          {data && data.pages > 1 && (
            <div className="flex items-center justify-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
              >
                <ChevronLeft className="h-4 w-4" />
                Previous
              </Button>
              <span className="text-sm text-muted-foreground">
                Page {page} of {data.pages}
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.min(data.pages, p + 1))}
                disabled={page === data.pages}
              >
                Next
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          )}

          {(!data?.wars || data.wars.length === 0) && (
            <div className="flex items-center justify-center h-32 text-muted-foreground">
              No wars recorded yet
            </div>
          )}
        </>
      )}
    </div>
  )
}
