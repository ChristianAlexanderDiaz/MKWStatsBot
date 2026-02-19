"""
Player repository: CRUD operations for players, roster, nicknames, and Discord linking.
"""

import json
import logging
from typing import List, Dict, Optional

from .base import BaseRepository


class PlayerRepository(BaseRepository):
    """Handles all player-related database operations."""

    def resolve_player_name(self, name_or_nickname: str, guild_id: int = 0, log_level: str = 'error') -> Optional[str]:
        """Resolve a name or nickname to players table player name.

        Args:
            name_or_nickname: The name or nickname to resolve
            guild_id: Guild ID for data isolation
            log_level: Logging level for database errors ('error', 'debug', 'none')
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Enhanced debug logging
                if log_level == 'debug':
                    logging.debug(f"🔍 [RESOLVE] Starting resolution for: '{name_or_nickname}' (guild_id: {guild_id})")

                # Strategy 1: Exact match with player_name
                strategy1_query = """
                    SELECT player_name FROM players
                    WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """
                if log_level == 'debug':
                    logging.debug(f"🔍 [STRATEGY1] Exact player_name match: {strategy1_query}")
                    logging.debug(f"🔍 [STRATEGY1] Parameters: ({name_or_nickname}, {guild_id})")

                cursor.execute(strategy1_query, (name_or_nickname, guild_id))
                result = cursor.fetchone()
                if result:
                    if log_level == 'debug':
                        logging.debug(f"✅ [STRATEGY1] Found exact player_name match: {result[0]}")
                    return result[0]
                elif log_level == 'debug':
                    logging.debug(f"❌ [STRATEGY1] No exact player_name match found")

                # Strategy 2: Case-insensitive match with player_name
                strategy2_query = """
                    SELECT player_name FROM players
                    WHERE LOWER(player_name) = LOWER(%s) AND guild_id = %s AND is_active = TRUE
                """
                if log_level == 'debug':
                    logging.debug(f"🔍 [STRATEGY2] Case-insensitive player_name match: {strategy2_query}")
                    logging.debug(f"🔍 [STRATEGY2] Parameters: ({name_or_nickname}, {guild_id})")

                cursor.execute(strategy2_query, (name_or_nickname, guild_id))
                result = cursor.fetchone()
                if result:
                    if log_level == 'debug':
                        logging.debug(f"✅ [STRATEGY2] Found case-insensitive player_name match: {result[0]}")
                    return result[0]
                elif log_level == 'debug':
                    logging.debug(f"❌ [STRATEGY2] No case-insensitive player_name match found")

                # Strategy 3: Exact nickname match (case-sensitive)
                strategy3_query = """
                    SELECT player_name FROM players
                    WHERE nicknames IS NOT NULL
                    AND nicknames ? %s
                    AND guild_id = %s
                    AND is_active = TRUE
                """
                if log_level == 'debug':
                    logging.debug(f"🔍 [STRATEGY3] Exact nickname match: {strategy3_query}")
                    logging.debug(f"🔍 [STRATEGY3] Parameters: ({name_or_nickname}, {guild_id})")

                cursor.execute(strategy3_query, (name_or_nickname, guild_id))
                result = cursor.fetchone()
                if result:
                    if log_level == 'debug':
                        logging.debug(f"✅ [STRATEGY3] Found exact nickname match: {result[0]}")
                    return result[0]
                elif log_level == 'debug':
                    logging.debug(f"❌ [STRATEGY3] No exact nickname match found")

                # Strategy 4: Case-insensitive nickname match (Python list approach)
                if log_level == 'debug':
                    logging.debug(f"🔍 [STRATEGY4] Starting Python list-based nickname matching")

                cursor.execute("""
                    SELECT player_name, nicknames
                    FROM players
                    WHERE guild_id = %s AND is_active = TRUE AND nicknames IS NOT NULL
                """, (guild_id,))

                nickname_results = cursor.fetchall()
                if log_level == 'debug':
                    logging.debug(f"🔍 [STRATEGY4] Found {len(nickname_results)} players with nicknames in guild {guild_id}")

                for player_name, nicknames in nickname_results:
                    if log_level == 'debug':
                        logging.debug(f"🔍 [STRATEGY4] Checking {player_name}: {nicknames} (type: {type(nicknames)})")

                    if isinstance(nicknames, list):
                        for nickname in nicknames:
                            if isinstance(nickname, str):
                                if log_level == 'debug':
                                    logging.debug(f"🔍 [STRATEGY4]   Testing nickname: '{nickname}' vs '{name_or_nickname}'")
                                    logging.debug(f"🔍 [STRATEGY4]   LOWER comparison: '{nickname.lower()}' == '{name_or_nickname.lower()}' => {nickname.lower() == name_or_nickname.lower()}")

                                if nickname.lower() == name_or_nickname.lower():
                                    if log_level == 'debug':
                                        logging.debug(f"✅ [STRATEGY4] Found case-insensitive nickname match: '{nickname}' -> {player_name}")
                                    return player_name
                    elif isinstance(nicknames, dict):
                        if log_level == 'debug':
                            logging.debug(f"🔍 [STRATEGY4]   Skipping dict (empty placeholder): {nicknames}")
                        continue
                    else:
                        if log_level == 'debug':
                            logging.debug(f"🔍 [STRATEGY4]   Unexpected nickname format: {type(nicknames)}")

                if log_level == 'debug':
                    logging.debug(f"❌ [STRATEGY4] No case-insensitive nickname match found")

                # Strategy 5: Alternative JSONB case-insensitive approach (fallback)
                try:
                    strategy5_query = """
                        SELECT player_name FROM players
                        WHERE guild_id = %s
                        AND is_active = TRUE
                        AND nicknames IS NOT NULL
                        AND LOWER(nicknames::text) LIKE LOWER(%s)
                    """
                    if log_level == 'debug':
                        logging.debug(f"🔍 [STRATEGY5] Alternative JSONB text search: {strategy5_query}")
                        logging.debug(f"🔍 [STRATEGY5] Parameters: ({guild_id}, '%{name_or_nickname}%')")

                    cursor.execute(strategy5_query, (guild_id, f'%"{name_or_nickname}"%'))
                    result = cursor.fetchone()
                    if result:
                        if log_level == 'debug':
                            logging.debug(f"✅ [STRATEGY5] Found alternative JSONB match: {result[0]}")
                        return result[0]
                    elif log_level == 'debug':
                        logging.debug(f"❌ [STRATEGY5] No alternative JSONB match found")

                except Exception as e:
                    if log_level == 'debug':
                        logging.debug(f"❌ [STRATEGY5] Alternative JSONB strategy failed: {e}")

                # Strategy 6: Match display_name (Discord display name)
                strategy6_query = """
                    SELECT player_name FROM players
                    WHERE LOWER(display_name) = LOWER(%s) AND guild_id = %s AND is_active = TRUE
                """
                if log_level == 'debug':
                    logging.debug(f"🔍 [STRATEGY6] Display name match: {strategy6_query}")
                    logging.debug(f"🔍 [STRATEGY6] Parameters: ({name_or_nickname}, {guild_id})")

                cursor.execute(strategy6_query, (name_or_nickname, guild_id))
                result = cursor.fetchone()
                if result:
                    if log_level == 'debug':
                        logging.debug(f"✅ [STRATEGY6] Found display_name match: {result[0]}")
                    return result[0]
                elif log_level == 'debug':
                    logging.debug(f"❌ [STRATEGY6] No display_name match found")

                # Strategy 7: Match discord_username (Discord username)
                strategy7_query = """
                    SELECT player_name FROM players
                    WHERE LOWER(discord_username) = LOWER(%s) AND guild_id = %s AND is_active = TRUE
                """
                if log_level == 'debug':
                    logging.debug(f"🔍 [STRATEGY7] Discord username match: {strategy7_query}")
                    logging.debug(f"🔍 [STRATEGY7] Parameters: ({name_or_nickname}, {guild_id})")

                cursor.execute(strategy7_query, (name_or_nickname, guild_id))
                result = cursor.fetchone()
                if result:
                    if log_level == 'debug':
                        logging.debug(f"✅ [STRATEGY7] Found discord_username match: {result[0]}")
                    return result[0]
                elif log_level == 'debug':
                    logging.debug(f"❌ [STRATEGY7] No discord_username match found")

                # Final debugging: show all available data
                if log_level == 'debug':
                    cursor.execute("""
                        SELECT player_name, nicknames
                        FROM players
                        WHERE guild_id = %s AND is_active = TRUE
                    """, (guild_id,))

                    all_players = cursor.fetchall()
                    logging.debug(f"🔍 [FINAL] Resolution failed for '{name_or_nickname}' in guild {guild_id}")
                    logging.debug(f"🔍 [FINAL] All active players in this guild:")
                    for player, nicknames in all_players:
                        logging.debug(f"🔍 [FINAL]   - {player}: {nicknames if nicknames else 'No nicknames'}")

                return None  # Not found

        except Exception as e:
            if log_level == 'error':
                logging.error(f"❌ Database error resolving player name '{name_or_nickname}' (guild: {guild_id}): {e}")
                import traceback
                logging.error(f"❌ Full traceback: {traceback.format_exc()}")
            elif log_level == 'debug':
                logging.debug(f"🔍 Database lookup failed for '{name_or_nickname}' (expected if opponent): {e}")
            return None

    def get_player_info(self, name_or_nickname: str, guild_id: int = 0) -> Optional[Dict]:
        """Get basic roster info for a player."""
        main_name = self.resolve_player_name(name_or_nickname, guild_id)
        if not main_name:
            return None

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT player_name, added_by, created_at, updated_at, team, nicknames
                    FROM players WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (main_name, guild_id))

                row = cursor.fetchone()
                if not row:
                    return None

                return {
                    'player_name': row[0],
                    'added_by': row[1],
                    'created_at': row[2].isoformat() if row[2] else None,
                    'updated_at': row[3].isoformat() if row[3] else None,
                    'team': row[4] if row[4] else 'Unassigned',
                    'nicknames': row[5] if row[5] else []
                }

        except Exception as e:
            logging.error(f"❌ Error getting player info: {e}")
            return None

    def get_all_players_stats(self, guild_id: int = 0) -> List[Dict]:
        """Get all roster players info."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT player_name, added_by, created_at, updated_at, team, nicknames, member_status, country_code, discord_user_id
                    FROM players
                    WHERE guild_id = %s AND is_active = TRUE
                    ORDER BY member_status, player_name
                """, (guild_id,))

                results = []
                for row in cursor.fetchall():
                    results.append({
                        'player_name': row[0],
                        'added_by': row[1],
                        'created_at': row[2].isoformat() if row[2] else None,
                        'updated_at': row[3].isoformat() if row[3] else None,
                        'team': row[4] if row[4] else 'Unassigned',
                        'nicknames': row[5] if row[5] else [],
                        'member_status': row[6] if row[6] else 'member',
                        'country_code': row[7] if row[7] else None,
                        'discord_user_id': row[8] if row[8] else None
                    })

                return results

        except Exception as e:
            logging.error(f"❌ Error getting all player stats: {e}")
            return []

    def get_all_players_stats_global(self, limit: Optional[int] = None) -> List[Dict]:
        """Get basic stats for all active players across all guilds for global leaderboard.

        Automatically excludes testing/dev guilds configured in EXCLUDED_GUILD_IDS env var.
        """
        from ..database import EXCLUDED_GUILD_IDS

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                query = """
                    SELECT player_name, guild_id, team, nicknames,
                           country_code, member_status
                    FROM players
                    WHERE is_active = TRUE
                """

                params = []
                if EXCLUDED_GUILD_IDS:
                    placeholders = ','.join(['%s'] * len(EXCLUDED_GUILD_IDS))
                    query += f" AND guild_id NOT IN ({placeholders})"
                    params.extend(EXCLUDED_GUILD_IDS)

                query += " ORDER BY player_name"

                if limit is not None:
                    query += " LIMIT %s"
                    params.append(limit)
                    cursor.execute(query, params)
                else:
                    cursor.execute(query, params) if params else cursor.execute(query)

                players = []
                for row in cursor.fetchall():
                    players.append({
                        'player_name': row[0],
                        'guild_id': row[1],
                        'team': row[2] or 'Unassigned',
                        'nicknames': row[3] or [],
                        'country_code': row[4] or None,
                        'member_status': row[5] or 'member',
                    })

                logging.info(f"✅ Retrieved {len(players)} active players globally")
                return players

        except Exception as e:
            logging.error(f"❌ Error getting global players: {e}")
            return []

    # Roster Management Methods

    def get_roster_players(self, guild_id: int = 0) -> List[str]:
        """Get list of active roster players."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT player_name FROM players
                    WHERE guild_id = %s AND is_active = TRUE
                    ORDER BY player_name
                """, (guild_id,))

                return [row[0] for row in cursor.fetchall()]

        except Exception as e:
            logging.error(f"❌ Error getting roster players: {e}")
            return []

    def add_roster_player(self, player_name: str, added_by: str = None, *, guild_id: int, member_status: str = 'member') -> bool:
        """Add a player to the active roster with optional member status."""
        self._validate_guild_id(guild_id, "add_roster_player")

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT id, is_active FROM players WHERE player_name = %s AND guild_id = %s
                """, (player_name, guild_id))

                existing = cursor.fetchone()
                if existing:
                    if existing[1]:  # Already active
                        logging.info(f"Player {player_name} is already in the active roster")
                        return False
                    else:
                        cursor.execute("""
                            UPDATE players
                            SET is_active = TRUE, updated_at = CURRENT_TIMESTAMP, added_by = %s, member_status = %s
                            WHERE player_name = %s AND guild_id = %s
                        """, (added_by, member_status, player_name, guild_id))
                        logging.info(f"✅ Reactivated player {player_name} in roster")
                else:
                    cursor.execute("""
                        INSERT INTO players (player_name, added_by, guild_id, member_status)
                        VALUES (%s, %s, %s, %s)
                    """, (player_name, added_by, guild_id, member_status))
                    logging.info(f"✅ Added player {player_name} to roster")

                conn.commit()
                return True

        except Exception as e:
            logging.error(f"❌ Error adding player to roster: {e}")
            return False

    def remove_roster_player(self, player_name: str, guild_id: int = 0) -> bool:
        """Remove a player from the active roster (mark as inactive)."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT id FROM players WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (player_name, guild_id))

                if not cursor.fetchone():
                    logging.info(f"Player {player_name} is not in the active roster")
                    return False

                cursor.execute("""
                    UPDATE players
                    SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP
                    WHERE player_name = %s AND guild_id = %s
                """, (player_name, guild_id))

                conn.commit()
                logging.info(f"✅ Removed player {player_name} from active roster")
                return True

        except Exception as e:
            logging.error(f"❌ Error removing player from roster: {e}")
            return False

    # Team Assignment Methods

    def set_player_team(self, player_name: str, team: str, guild_id: int = 0) -> bool:
        """Set a player's team assignment."""
        # Get valid teams via guild repository (accessed through db_manager)
        valid_teams = self._db.guilds.get_guild_team_names(guild_id)
        valid_teams.append('Unassigned')

        if team not in valid_teams:
            logging.error(f"Invalid team '{team}'. Valid teams for guild {guild_id}: {valid_teams}")
            return False

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT id FROM players WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (player_name, guild_id))

                if not cursor.fetchone():
                    logging.error(f"Player {player_name} not found in active roster")
                    return False

                cursor.execute("""
                    UPDATE players
                    SET team = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (team, player_name, guild_id))

                conn.commit()
                logging.info(f"✅ Set {player_name}'s team to {team}")
                return True

        except Exception as e:
            logging.error(f"❌ Error setting player team: {e}")
            return False

    def get_players_by_team(self, team: str = None, guild_id: int = 0) -> Dict[str, List[str]]:
        """Get players organized by team, or players from a specific team."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                if team:
                    cursor.execute("""
                        SELECT player_name FROM players
                        WHERE team = %s AND guild_id = %s AND is_active = TRUE
                        ORDER BY player_name
                    """, (team, guild_id))

                    return {team: [row[0] for row in cursor.fetchall()]}
                else:
                    cursor.execute("""
                        SELECT team, player_name FROM players
                        WHERE guild_id = %s AND is_active = TRUE
                        ORDER BY team, player_name
                    """, (guild_id,))

                    teams = {}
                    for row in cursor.fetchall():
                        team_name, player_name = row
                        if team_name not in teams:
                            teams[team_name] = []
                        teams[team_name].append(player_name)

                    return teams

        except Exception as e:
            logging.error(f"❌ Error getting players by team: {e}")
            return {}

    def get_team_roster(self, team: str, guild_id: int = 0) -> List[str]:
        """Get list of players in a specific team."""
        team_data = self.get_players_by_team(team, guild_id)
        return team_data.get(team, [])

    def get_player_team(self, player_name: str, guild_id: int = 0) -> Optional[str]:
        """Get a player's current team assignment."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT team FROM players
                    WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (player_name, guild_id))

                result = cursor.fetchone()
                return result[0] if result else None

        except Exception as e:
            logging.error(f"❌ Error getting player team: {e}")
            return None

    # Nickname Management Methods

    def add_nickname(self, player_name: str, nickname: str, guild_id: int = 0) -> bool:
        """Add a nickname to a player's nickname list."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT nicknames FROM players
                    WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (player_name, guild_id))

                result = cursor.fetchone()
                if not result:
                    logging.error(f"Player {player_name} not found in active roster")
                    return False

                current_nicknames = result[0] if result[0] else []

                if nickname in current_nicknames:
                    logging.info(f"Nickname '{nickname}' already exists for {player_name}")
                    return False

                updated_nicknames = current_nicknames + [nickname]

                cursor.execute("""
                    UPDATE players
                    SET nicknames = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (json.dumps(updated_nicknames), player_name, guild_id))

                conn.commit()
                logging.info(f"✅ Added nickname '{nickname}' to {player_name}")
                return True

        except Exception as e:
            logging.error(f"❌ Error adding nickname: {e}")
            return False

    def remove_nickname(self, player_name: str, nickname: str, guild_id: int = 0) -> bool:
        """Remove a nickname from a player's nickname list."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT nicknames FROM players
                    WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (player_name, guild_id))

                result = cursor.fetchone()
                if not result:
                    logging.error(f"Player {player_name} not found in active roster")
                    return False

                current_nicknames = result[0] if result[0] else []

                if nickname not in current_nicknames:
                    logging.info(f"Nickname '{nickname}' not found for {player_name}")
                    return False

                updated_nicknames = [n for n in current_nicknames if n != nickname]

                cursor.execute("""
                    UPDATE players
                    SET nicknames = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (json.dumps(updated_nicknames), player_name, guild_id))

                conn.commit()
                logging.info(f"✅ Removed nickname '{nickname}' from {player_name}")
                return True

        except Exception as e:
            logging.error(f"❌ Error removing nickname: {e}")
            return False

    def get_player_nicknames(self, player_name: str, guild_id: int = 0) -> List[str]:
        """Get all nicknames for a player."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT nicknames FROM players
                    WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (player_name, guild_id))

                result = cursor.fetchone()
                return result[0] if result and result[0] else []

        except Exception as e:
            logging.error(f"❌ Error getting player nicknames: {e}")
            return []

    def set_player_nicknames(self, player_name: str, nicknames: List[str], guild_id: int = 0) -> bool:
        """Set all nicknames for a player (replaces existing nicknames)."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT id FROM players WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (player_name, guild_id))

                if not cursor.fetchone():
                    logging.error(f"Player {player_name} not found in active roster")
                    return False

                unique_nicknames = []
                for nickname in nicknames:
                    if nickname not in unique_nicknames:
                        unique_nicknames.append(nickname)

                cursor.execute("""
                    UPDATE players
                    SET nicknames = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (json.dumps(unique_nicknames), player_name, guild_id))

                conn.commit()
                logging.info(f"✅ Set nicknames for {player_name}: {unique_nicknames}")
                return True

        except Exception as e:
            logging.error(f"❌ Error setting player nicknames: {e}")
            return False

    # Member Status Methods

    def set_player_member_status(self, player_name: str, member_status: str, guild_id: int = 0) -> bool:
        """Set the member status for a player."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                resolved_player = self.resolve_player_name(player_name, guild_id)
                if not resolved_player:
                    logging.error(f"Player {player_name} not found in guild {guild_id}")
                    return False

                cursor.execute("""
                    UPDATE players
                    SET member_status = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (member_status, resolved_player, guild_id))

                if cursor.rowcount == 0:
                    logging.error(f"No active player {resolved_player} found to update")
                    return False

                conn.commit()
                logging.info(f"✅ Updated {resolved_player} member status to {member_status}")
                return True

        except Exception as e:
            logging.error(f"❌ Error setting member status: {e}")
            return False

    def get_players_by_member_status(self, member_status: str, guild_id: int = 0) -> List[Dict]:
        """Get all players with a specific member status."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT player_name, team, nicknames, created_at, updated_at
                    FROM players
                    WHERE member_status = %s AND guild_id = %s AND is_active = TRUE
                    ORDER BY player_name
                """, (member_status, guild_id))

                results = cursor.fetchall()
                players = []

                for row in results:
                    players.append({
                        'player_name': row[0],
                        'team': row[1] or 'Unassigned',
                        'nicknames': row[2] or [],
                        'created_at': row[3],
                        'updated_at': row[4],
                        'member_status': member_status
                    })

                return players

        except Exception as e:
            logging.error(f"❌ Error getting players by member status: {e}")
            return []

    def get_member_status_counts(self, guild_id: int = 0) -> Dict[str, int]:
        """Get count of players by member status."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT member_status, COUNT(*)
                    FROM players
                    WHERE guild_id = %s AND is_active = TRUE
                    GROUP BY member_status
                """, (guild_id,))

                results = cursor.fetchall()
                return {status: count for status, count in results}

        except Exception as e:
            logging.error(f"❌ Error getting member status counts: {e}")
            return {}

    # Discord User ID Support Methods

    def add_roster_player_with_discord(
        self,
        discord_user_id: int,
        player_name: str,
        display_name: str,
        discord_username: str,
        member_status: str,
        added_by: str = None,
        *,
        guild_id: int,
        country_code: str = None
    ) -> bool:
        """Add a player to the active roster with Discord user ID."""
        self._validate_guild_id(guild_id, "add_roster_player_with_discord")

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT id, is_active, player_name FROM players
                    WHERE discord_user_id = %s AND guild_id = %s
                """, (discord_user_id, guild_id))

                existing = cursor.fetchone()
                if existing:
                    if existing[1]:  # Already active
                        logging.info(f"Player with Discord ID {discord_user_id} is already in the active roster as {existing[2]}")
                        return False
                    else:
                        cursor.execute("""
                            UPDATE players
                            SET is_active = TRUE,
                                player_name = %s,
                                display_name = %s,
                                discord_username = %s,
                                member_status = %s,
                                country_code = %s,
                                updated_at = CURRENT_TIMESTAMP,
                                added_by = %s,
                                last_role_sync = CURRENT_TIMESTAMP
                            WHERE discord_user_id = %s AND guild_id = %s
                        """, (player_name, display_name, discord_username, member_status, country_code, added_by, discord_user_id, guild_id))
                        logging.info(f"✅ Reactivated player {player_name} (Discord ID: {discord_user_id})")
                else:
                    cursor.execute("""
                        INSERT INTO players (
                            discord_user_id, player_name, display_name, discord_username,
                            member_status, added_by, guild_id, country_code, last_role_sync
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    """, (discord_user_id, player_name, display_name, discord_username, member_status, added_by, guild_id, country_code))
                    logging.info(f"✅ Added player {player_name} with Discord ID {discord_user_id}")

                conn.commit()
                return True

        except Exception as e:
            logging.error(f"❌ Error adding player with Discord ID to roster: {e}")
            return False

    def link_player_to_discord_user(
        self,
        player_name: str,
        discord_user_id: int,
        display_name: str,
        discord_username: str,
        member_status: str,
        guild_id: int = 0
    ) -> bool:
        """Link an existing player to a Discord user."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT id, discord_user_id FROM players
                    WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (player_name, guild_id))

                result = cursor.fetchone()
                if not result:
                    logging.error(f"Player {player_name} not found in active roster")
                    return False

                if result[1] is not None:
                    logging.warning(f"Player {player_name} is already linked to Discord ID {result[1]}")
                    return False

                cursor.execute("""
                    UPDATE players
                    SET discord_user_id = %s,
                        display_name = %s,
                        discord_username = %s,
                        member_status = %s,
                        last_role_sync = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE player_name = %s AND guild_id = %s
                """, (discord_user_id, display_name, discord_username, member_status, player_name, guild_id))

                conn.commit()
                logging.info(f"✅ Linked player {player_name} to Discord ID {discord_user_id}")
                return True

        except Exception as e:
            logging.error(f"❌ Error linking player to Discord user: {e}")
            return False

    def sync_player_discord_info(
        self,
        discord_user_id: int,
        display_name: str,
        discord_username: str,
        guild_id: int = 0
    ) -> bool:
        """Sync player's display name and Discord username from Discord."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    UPDATE players
                    SET display_name = %s,
                        discord_username = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE discord_user_id = %s AND guild_id = %s
                """, (display_name, discord_username, discord_user_id, guild_id))

                if cursor.rowcount > 0:
                    conn.commit()
                    logging.debug(f"✅ Synced Discord info for user {discord_user_id}")
                    return True
                else:
                    logging.debug(f"No player found with Discord ID {discord_user_id} in guild {guild_id}")
                    return False

        except Exception as e:
            logging.error(f"❌ Error syncing player Discord info: {e}")
            return False

    def sync_player_role(
        self,
        discord_user_id: int,
        member_status: str,
        guild_id: int = 0
    ) -> bool:
        """Sync player's member_status from their Discord role."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    UPDATE players
                    SET member_status = %s,
                        last_role_sync = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE discord_user_id = %s AND guild_id = %s
                """, (member_status, discord_user_id, guild_id))

                if cursor.rowcount > 0:
                    conn.commit()
                    logging.debug(f"✅ Synced role for Discord user {discord_user_id} to {member_status}")
                    return True
                else:
                    logging.debug(f"No player found with Discord ID {discord_user_id} in guild {guild_id}")
                    return False

        except Exception as e:
            logging.error(f"❌ Error syncing player role: {e}")
            return False

    def get_unlinked_players(self, guild_id: int = 0) -> List[Dict]:
        """Get all active players without a Discord user ID link."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT player_name, team, member_status, total_score, war_count
                    FROM players
                    WHERE discord_user_id IS NULL
                    AND is_active = TRUE
                    AND guild_id = %s
                    ORDER BY player_name
                """, (guild_id,))

                players = []
                for row in cursor.fetchall():
                    players.append({
                        'player_name': row[0],
                        'team': row[1],
                        'member_status': row[2],
                        'total_score': row[3],
                        'war_count': float(row[4]) if row[4] else 0
                    })

                return players

        except Exception as e:
            logging.error(f"❌ Error getting unlinked players: {e}")
            return []
