/**
 * API client for the MKW Dashboard
 * Communicates with the FastAPI backend
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// ==================== Types ====================

export interface User {
  id: number
  username: string
  avatar: string | null
  guilds: Record<string, GuildPermissions>
}

export interface GuildPermissions {
  is_admin: boolean
  can_manage: boolean
  guild_name: string
}

export interface Guild {
  id: string
  name: string
  is_admin: boolean
  can_manage: boolean
  is_configured: boolean
}

export interface Player {
  name: string
  team: string
  nicknames: string[]
  member_status: 'member' | 'trial' | 'ally' | 'kicked'
  total_score: number
  total_races: number
  war_count: number
  average_score: number
  last_war_date: string | null
  is_active: boolean
  created_at: string | null
}

export interface War {
  id: number
  war_date: string
  race_count: number
  players: WarPlayer[]
  team_score: number
  team_differential: number
  created_at: string
}

export interface WarPlayer {
  name: string
  score: number
  races_played?: number
}

export interface LeaderboardEntry {
  rank: number
  name: string
  team: string
  member_status: string
  total_score: number
  war_count: number
  average_score: number
  total_team_differential: number
  last_war_date: string | null
}

export interface GuildOverview {
  total_players: number
  member_counts: Record<string, number>
  total_wars: number
  average_differential: number
  wins: number
  losses: number
}

export interface BulkSession {
  id: number
  guild_id: number
  created_by_user_id: number
  status: string
  total_images: number
  created_at: string
  expires_at: string
}

export interface BulkResult {
  id: number
  image_filename: string
  image_url: string | null
  detected_players: BulkPlayer[]
  review_status: 'pending' | 'approved' | 'rejected'
  corrected_players: BulkPlayer[] | null
  race_count: number
  message_timestamp: string | null
  created_at: string
}

export interface BulkPlayer {
  name: string
  score: number
  raw_name?: string
  is_roster_member?: boolean
  races_played?: number
}

export interface BulkFailure {
  id: number
  image_filename: string | null
  image_url: string | null
  error_message: string
  message_timestamp: string | null
  discord_message_id: number | null
  created_at: string
}

// ==================== Helper Functions ====================

function getAuthHeaders(token?: string): HeadersInit {
  const headers: HeadersInit = {
    'Content-Type': 'application/json'
  }
  const sessionToken = token || (typeof window !== 'undefined' ? localStorage.getItem('session_token') : null)
  if (sessionToken) {
    headers['Authorization'] = `Bearer ${sessionToken}`
  }
  return headers
}

async function fetchApi<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T | null> {
  try {
    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      ...options,
      headers: {
        ...getAuthHeaders(),
        ...options.headers
      }
    })
    if (!response.ok) {
      console.error(`API error: ${response.status} ${response.statusText}`)
      return null
    }
    return await response.json()
  } catch (error) {
    console.error(`Failed to fetch ${endpoint}:`, error)
    return null
  }
}

// ==================== API Object ====================

export const api = {
  // Auth
  getLoginUrl: () => `${API_BASE_URL}/api/auth/discord`,

  getCurrentUser: async (token: string): Promise<User | null> => {
    return fetchApi<User>('/api/auth/me', {
      headers: { Authorization: `Bearer ${token}` }
    })
  },

  logout: async (token: string): Promise<boolean> => {
    const response = await fetch(`${API_BASE_URL}/api/auth/logout`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` }
    })
    return response.ok
  },

  // Guilds
  getGuilds: async (): Promise<Guild[]> => {
    const result = await fetchApi<Guild[]>('/api/guilds')
    return result || []
  },

  getGuild: async (guildId: string): Promise<{ config: any; overview: GuildOverview } | null> => {
    return fetchApi(`/api/guilds/${guildId}`)
  },

  // Players
  getPlayers: async (guildId: string): Promise<{ players: Player[]; total: number }> => {
    const result = await fetchApi<{ players: Player[]; total: number }>(
      `/api/guilds/${guildId}/players`
    )
    return result || { players: [], total: 0 }
  },

  getAllPlayers: async (guildId: string): Promise<{ players: Player[]; total: number }> => {
    const result = await fetchApi<{ players: Player[]; total: number }>(
      `/api/guilds/${guildId}/players?include_inactive=true`
    )
    return result || { players: [], total: 0 }
  },

  getPlayer: async (guildId: string, playerName: string): Promise<Player | null> => {
    return fetchApi(`/api/guilds/${guildId}/players/${encodeURIComponent(playerName)}`)
  },

  addPlayer: async (guildId: string, name: string, memberStatus: string = 'member'): Promise<boolean> => {
    const response = await fetch(`${API_BASE_URL}/api/guilds/${guildId}/players`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ name, member_status: memberStatus })
    })
    return response.ok
  },

  updatePlayerStatus: async (guildId: string, playerName: string, memberStatus: string): Promise<boolean> => {
    const response = await fetch(
      `${API_BASE_URL}/api/guilds/${guildId}/players/${encodeURIComponent(playerName)}/status`,
      {
        method: 'PUT',
        headers: getAuthHeaders(),
        body: JSON.stringify({ member_status: memberStatus })
      }
    )
    return response.ok
  },

  addNickname: async (guildId: string, playerName: string, nickname: string): Promise<boolean> => {
    const response = await fetch(
      `${API_BASE_URL}/api/guilds/${guildId}/players/${encodeURIComponent(playerName)}/nicknames`,
      {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ nickname })
      }
    )
    return response.ok
  },

  // Wars
  getWars: async (guildId: string, page: number = 1, limit: number = 20): Promise<{
    wars: War[]
    page: number
    limit: number
    total: number
    pages: number
  }> => {
    const result = await fetchApi<any>(`/api/guilds/${guildId}/wars?page=${page}&limit=${limit}`)
    return result || { wars: [], page: 1, limit: 20, total: 0, pages: 0 }
  },

  getWar: async (guildId: string, warId: number): Promise<War | null> => {
    return fetchApi(`/api/guilds/${guildId}/wars/${warId}`)
  },

  // Stats
  getOverview: async (guildId: string): Promise<GuildOverview | null> => {
    return fetchApi(`/api/guilds/${guildId}/stats/overview`)
  },

  getLeaderboard: async (
    guildId: string,
    sortBy: string = 'average_score',
    limit: number = 50
  ): Promise<{ leaderboard: LeaderboardEntry[]; sort_by: string }> => {
    const result = await fetchApi<any>(
      `/api/guilds/${guildId}/stats/leaderboard?sort=${sortBy}&limit=${limit}`
    )
    return result || { leaderboard: [], sort_by: sortBy }
  },

  getPlayerStats: async (guildId: string, playerName: string): Promise<Player | null> => {
    return fetchApi(`/api/guilds/${guildId}/stats/player/${encodeURIComponent(playerName)}`)
  },

  // Bulk Review
  getBulkSession: async (token: string): Promise<BulkSession | null> => {
    return fetchApi(`/api/bulk/sessions/${token}`)
  },

  getBulkResults: async (token: string): Promise<{
    session: BulkSession
    results: BulkResult[]
    failures: BulkFailure[]
    total: number
  } | null> => {
    return fetchApi(`/api/bulk/sessions/${token}/results`)
  },

  updateBulkResult: async (
    sessionToken: string,
    resultId: number,
    reviewStatus: 'pending' | 'approved' | 'rejected',
    correctedPlayers?: BulkPlayer[]
  ): Promise<boolean> => {
    const response = await fetch(
      `${API_BASE_URL}/api/bulk/sessions/${sessionToken}/results/${resultId}`,
      {
        method: 'PUT',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          review_status: reviewStatus,
          corrected_players: correctedPlayers
        })
      }
    )
    return response.ok
  },

  confirmBulkSession: async (sessionToken: string): Promise<{
    status: string
    wars_created: number
    war_ids: number[]
  } | null> => {
    const response = await fetch(`${API_BASE_URL}/api/bulk/sessions/${sessionToken}/confirm`, {
      method: 'POST',
      headers: getAuthHeaders()
    })
    if (!response.ok) return null
    return response.json()
  },

  cancelBulkSession: async (sessionToken: string): Promise<boolean> => {
    const response = await fetch(`${API_BASE_URL}/api/bulk/sessions/${sessionToken}/cancel`, {
      method: 'POST',
      headers: getAuthHeaders()
    })
    return response.ok
  }
}

// Export individual functions for backwards compatibility
export const {
  getLoginUrl,
  getCurrentUser,
  logout,
  getGuilds,
  getGuild,
  getPlayers,
  getPlayer,
  addPlayer,
  updatePlayerStatus,
  addNickname,
  getWars,
  getWar,
  getOverview,
  getLeaderboard,
  getPlayerStats,
  getBulkSession,
  getBulkResults,
  updateBulkResult,
  confirmBulkSession,
  cancelBulkSession
} = api
