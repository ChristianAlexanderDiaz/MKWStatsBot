"use client"

import { useAuth } from "@/lib/auth"
import { api } from "@/lib/api"
import { useQuery } from "@tanstack/react-query"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { useState } from "react"

const sortOptions = [
  { value: "average_score", label: "Average Score" },
  { value: "total_score", label: "Total Score" },
  { value: "war_count", label: "Wars Played" },
  { value: "total_team_differential", label: "Team Differential" },
]

export default function LeaderboardPage() {
  const { selectedGuild } = useAuth()
  const [sortBy, setSortBy] = useState("average_score")

  const { data, isLoading } = useQuery({
    queryKey: ["leaderboard", selectedGuild?.id, sortBy],
    queryFn: () => api.getLeaderboard(selectedGuild!.id, sortBy, 50),
    enabled: !!selectedGuild,
  })

  if (!selectedGuild) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-muted-foreground">Select a guild to view leaderboard</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Leaderboard</h1>
          <p className="text-muted-foreground">
            Top performers in {selectedGuild.name}
          </p>
        </div>
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value)}
          className="rounded-md border bg-background px-3 py-2 text-sm"
        >
          {sortOptions.map((option) => (
            <option key={option.value} value={option.value}>
              Sort by: {option.label}
            </option>
          ))}
        </select>
      </div>

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex items-center justify-center h-64">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="h-12 px-4 text-left align-middle font-medium text-muted-foreground">
                      Rank
                    </th>
                    <th className="h-12 px-4 text-left align-middle font-medium text-muted-foreground">
                      Player
                    </th>
                    <th className="h-12 px-4 text-left align-middle font-medium text-muted-foreground">
                      Team
                    </th>
                    <th className="h-12 px-4 text-right align-middle font-medium text-muted-foreground">
                      Avg Score
                    </th>
                    <th className="h-12 px-4 text-right align-middle font-medium text-muted-foreground">
                      Wars
                    </th>
                    <th className="h-12 px-4 text-right align-middle font-medium text-muted-foreground">
                      Differential
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data?.leaderboard.map((entry) => (
                    <tr
                      key={entry.name}
                      className="border-b transition-colors hover:bg-muted/50"
                    >
                      <td className="p-4 align-middle">
                        <span
                          className={`inline-flex h-8 w-8 items-center justify-center rounded-full font-bold ${
                            entry.rank === 1
                              ? "bg-yellow-100 text-yellow-700"
                              : entry.rank === 2
                              ? "bg-gray-100 text-gray-700"
                              : entry.rank === 3
                              ? "bg-orange-100 text-orange-700"
                              : "bg-muted text-muted-foreground"
                          }`}
                        >
                          {entry.rank}
                        </span>
                      </td>
                      <td className="p-4 align-middle">
                        <div className="flex items-center gap-2">
                          <span className="font-medium">{entry.name}</span>
                          <Badge
                            variant={
                              entry.member_status === "member"
                                ? "default"
                                : entry.member_status === "trial"
                                ? "warning"
                                : entry.member_status === "ally"
                                ? "secondary"
                                : "destructive"
                            }
                          >
                            {entry.member_status}
                          </Badge>
                        </div>
                      </td>
                      <td className="p-4 align-middle text-muted-foreground">
                        {entry.team || "Unassigned"}
                      </td>
                      <td className="p-4 align-middle text-right font-medium">
                        {entry.average_score.toFixed(1)}
                      </td>
                      <td className="p-4 align-middle text-right">
                        {entry.war_count.toFixed(1)}
                      </td>
                      <td
                        className={`p-4 align-middle text-right font-medium ${
                          entry.total_team_differential >= 0
                            ? "text-green-600"
                            : "text-red-600"
                        }`}
                      >
                        {entry.total_team_differential >= 0 ? "+" : ""}
                        {entry.total_team_differential}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {(!data?.leaderboard || data.leaderboard.length === 0) && (
                <div className="flex items-center justify-center h-32 text-muted-foreground">
                  No players with war history found
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
