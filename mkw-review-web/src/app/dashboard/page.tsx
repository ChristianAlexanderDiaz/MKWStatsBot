"use client"

import { useAuth } from "@/lib/auth"
import { api, GuildOverview } from "@/lib/api"
import { useQuery } from "@tanstack/react-query"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Users, Swords, TrendingUp, TrendingDown, Trophy } from "lucide-react"

export default function DashboardPage() {
  const { selectedGuild } = useAuth()

  const { data: overview, isLoading } = useQuery({
    queryKey: ["overview", selectedGuild?.id],
    queryFn: () => api.getOverview(selectedGuild!.id),
    enabled: !!selectedGuild,
  })

  if (!selectedGuild) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-muted-foreground">Select a guild to view dashboard</p>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    )
  }

  const stats = overview || {
    total_players: 0,
    member_counts: {},
    total_wars: 0,
    average_differential: 0,
    wins: 0,
    losses: 0,
  }

  const winRate = stats.total_wars > 0
    ? ((stats.wins / stats.total_wars) * 100).toFixed(1)
    : "0.0"

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">
          Overview of {selectedGuild.name}
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Players</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.total_players}</div>
            <p className="text-xs text-muted-foreground">
              {stats.member_counts?.member || 0} members, {stats.member_counts?.trial || 0} trials
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Wars</CardTitle>
            <Swords className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.total_wars}</div>
            <p className="text-xs text-muted-foreground">
              {stats.wins} wins, {stats.losses} losses
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Win Rate</CardTitle>
            <Trophy className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{winRate}%</div>
            <p className="text-xs text-muted-foreground">
              Based on team differential
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Avg Differential</CardTitle>
            {stats.average_differential >= 0 ? (
              <TrendingUp className="h-4 w-4 text-green-500" />
            ) : (
              <TrendingDown className="h-4 w-4 text-red-500" />
            )}
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold ${
              stats.average_differential >= 0 ? "text-green-500" : "text-red-500"
            }`}>
              {stats.average_differential >= 0 ? "+" : ""}
              {stats.average_differential.toFixed(1)}
            </div>
            <p className="text-xs text-muted-foreground">
              Points per war vs breakeven
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Quick Actions */}
      <Card>
        <CardHeader>
          <CardTitle>Quick Actions</CardTitle>
          <CardDescription>Common tasks for managing your guild</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-3">
          <a
            href="/dashboard/leaderboard"
            className="flex items-center gap-3 rounded-lg border p-4 hover:bg-muted transition-colors"
          >
            <Trophy className="h-8 w-8 text-yellow-500" />
            <div>
              <h3 className="font-medium">View Leaderboard</h3>
              <p className="text-sm text-muted-foreground">See top performers</p>
            </div>
          </a>
          <a
            href="/dashboard/players"
            className="flex items-center gap-3 rounded-lg border p-4 hover:bg-muted transition-colors"
          >
            <Users className="h-8 w-8 text-blue-500" />
            <div>
              <h3 className="font-medium">Manage Roster</h3>
              <p className="text-sm text-muted-foreground">Add or edit players</p>
            </div>
          </a>
          <a
            href="/dashboard/wars"
            className="flex items-center gap-3 rounded-lg border p-4 hover:bg-muted transition-colors"
          >
            <Swords className="h-8 w-8 text-purple-500" />
            <div>
              <h3 className="font-medium">War History</h3>
              <p className="text-sm text-muted-foreground">View past wars</p>
            </div>
          </a>
        </CardContent>
      </Card>
    </div>
  )
}
