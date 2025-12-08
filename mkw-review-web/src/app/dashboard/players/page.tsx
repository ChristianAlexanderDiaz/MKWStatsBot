"use client"

import { useAuth } from "@/lib/auth"
import { api, Player } from "@/lib/api"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { useState } from "react"
import { Plus, Search, UserPlus } from "lucide-react"

const statusOptions = ["member", "trial", "ally", "kicked"] as const

export default function PlayersPage() {
  const { selectedGuild } = useAuth()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState("")
  const [showAddModal, setShowAddModal] = useState(false)
  const [newPlayerName, setNewPlayerName] = useState("")
  const [newPlayerStatus, setNewPlayerStatus] = useState<string>("member")

  const { data, isLoading } = useQuery({
    queryKey: ["players", selectedGuild?.id],
    queryFn: () => api.getPlayers(selectedGuild!.id),
    enabled: !!selectedGuild,
  })

  const addPlayerMutation = useMutation({
    mutationFn: () => api.addPlayer(selectedGuild!.id, newPlayerName, newPlayerStatus),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["players", selectedGuild?.id] })
      setShowAddModal(false)
      setNewPlayerName("")
      setNewPlayerStatus("member")
    },
  })

  const updateStatusMutation = useMutation({
    mutationFn: ({ name, status }: { name: string; status: string }) =>
      api.updatePlayerStatus(selectedGuild!.id, name, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["players", selectedGuild?.id] })
    },
  })

  if (!selectedGuild) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-muted-foreground">Select a guild to view roster</p>
      </div>
    )
  }

  const filteredPlayers = data?.players.filter((player) =>
    player.name.toLowerCase().includes(search.toLowerCase()) ||
    player.nicknames.some((n) => n.toLowerCase().includes(search.toLowerCase()))
  ) || []

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Roster</h1>
          <p className="text-muted-foreground">
            {data?.total || 0} players in {selectedGuild.name}
          </p>
        </div>
        <Button onClick={() => setShowAddModal(true)}>
          <UserPlus className="mr-2 h-4 w-4" />
          Add Player
        </Button>
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Search players or nicknames..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="pl-9"
        />
      </div>

      {/* Add Player Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <Card className="w-full max-w-md">
            <CardHeader>
              <CardTitle>Add New Player</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="text-sm font-medium">Player Name</label>
                <Input
                  value={newPlayerName}
                  onChange={(e) => setNewPlayerName(e.target.value)}
                  placeholder="Enter player name"
                />
              </div>
              <div>
                <label className="text-sm font-medium">Member Status</label>
                <select
                  value={newPlayerStatus}
                  onChange={(e) => setNewPlayerStatus(e.target.value)}
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                >
                  {statusOptions.map((status) => (
                    <option key={status} value={status}>
                      {status.charAt(0).toUpperCase() + status.slice(1)}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={() => setShowAddModal(false)}>
                  Cancel
                </Button>
                <Button
                  onClick={() => addPlayerMutation.mutate()}
                  disabled={!newPlayerName || addPlayerMutation.isPending}
                >
                  {addPlayerMutation.isPending ? "Adding..." : "Add Player"}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Players Table */}
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
                      Name
                    </th>
                    <th className="h-12 px-4 text-left align-middle font-medium text-muted-foreground">
                      Nicknames
                    </th>
                    <th className="h-12 px-4 text-left align-middle font-medium text-muted-foreground">
                      Team
                    </th>
                    <th className="h-12 px-4 text-left align-middle font-medium text-muted-foreground">
                      Status
                    </th>
                    <th className="h-12 px-4 text-right align-middle font-medium text-muted-foreground">
                      Avg Score
                    </th>
                    <th className="h-12 px-4 text-right align-middle font-medium text-muted-foreground">
                      Wars
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {filteredPlayers.map((player) => (
                    <tr
                      key={player.name}
                      className="border-b transition-colors hover:bg-muted/50"
                    >
                      <td className="p-4 align-middle font-medium">
                        {player.name}
                      </td>
                      <td className="p-4 align-middle text-muted-foreground">
                        {player.nicknames.length > 0
                          ? player.nicknames.slice(0, 3).join(", ")
                          : "-"}
                        {player.nicknames.length > 3 && ` +${player.nicknames.length - 3}`}
                      </td>
                      <td className="p-4 align-middle text-muted-foreground">
                        {player.team || "Unassigned"}
                      </td>
                      <td className="p-4 align-middle">
                        <select
                          value={player.member_status}
                          onChange={(e) =>
                            updateStatusMutation.mutate({
                              name: player.name,
                              status: e.target.value,
                            })
                          }
                          className={`rounded-md border-none bg-transparent px-2 py-1 text-sm font-medium ${
                            player.member_status === "member"
                              ? "text-blue-600"
                              : player.member_status === "trial"
                              ? "text-yellow-600"
                              : player.member_status === "ally"
                              ? "text-green-600"
                              : "text-red-600"
                          }`}
                        >
                          {statusOptions.map((status) => (
                            <option key={status} value={status}>
                              {status.charAt(0).toUpperCase() + status.slice(1)}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="p-4 align-middle text-right">
                        {player.average_score.toFixed(1)}
                      </td>
                      <td className="p-4 align-middle text-right">
                        {player.war_count.toFixed(1)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {filteredPlayers.length === 0 && (
                <div className="flex items-center justify-center h-32 text-muted-foreground">
                  {search ? "No players match your search" : "No players in roster"}
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
