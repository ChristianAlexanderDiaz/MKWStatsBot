/**
 * Shared TypeScript types for the MKW Dashboard
 */

export interface BulkSession {
  id: number
  guild_id: string
  created_by_user_id: string
  status: string
  total_images: number
  created_at: string
  expires_at: string
}

export interface BulkPlayer {
  name: string
  score: number
  raw_name?: string
  is_roster_member?: boolean
  races_played?: number
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

export interface BulkFailure {
  id: number
  image_filename: string | null
  image_url: string | null
  error_message: string
  message_timestamp: string | null
  discord_message_id: string | null
  created_at: string
}

export interface StagedPlayer {
  name: string
  memberStatus: string
}

export interface GuildConfig {
  [key: string]: unknown
}
