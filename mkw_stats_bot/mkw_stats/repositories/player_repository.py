"""
Player repository: CRUD operations for players, roster, nicknames, and Discord linking.
"""

import logging
import traceback

from ..constants import EXCLUDED_GUILD_IDS
from .base import BaseRepository


class PlayerRepository(BaseRepository):
    """Handles all player-related database operations."""

    async def resolve_player_name(self, name_or_nickname: str, guild_id: int = 0, log_level: str = 'error') -> str | None:
        """Resolve a name or nickname to players table player name.

        Args:
            name_or_nickname: The name or nickname to resolve
            guild_id: Guild ID for data isolation
            log_level: Logging level for database errors ('error', 'debug', 'none')
        """
        if not guild_id:
            if log_level != 'none':
                logging.warning(f"resolve_player_name called with invalid guild_id={guild_id!r} for name '{name_or_nickname}'")
            return None

        try:
            async with self.get_connection() as conn:

                # Enhanced debug logging
                if log_level == 'debug':
                    logging.debug(f"[RESOLVE] Starting resolution for: '{name_or_nickname}' (guild_id: {guild_id})")

                # Strategy 1: Exact match with player_name
                strategy1_query = """
                    SELECT player_name FROM players
                    WHERE player_name = $1 AND guild_id = $2 AND is_active = TRUE
                """
                if log_level == 'debug':
                    logging.debug(f"[STRATEGY1] Exact player_name match: {strategy1_query}")
                    logging.debug(f"[STRATEGY1] Parameters: ({name_or_nickname}, {guild_id})")

                result = await conn.fetchrow(strategy1_query, name_or_nickname, guild_id)
                if result:
                    if log_level == 'debug':
                        logging.debug(f"[STRATEGY1] Found exact player_name match: {result[0]}")
                    return result[0]
                elif log_level == 'debug':
                    logging.debug("[STRATEGY1] No exact player_name match found")

                # Strategy 2: Case-insensitive match with player_name
                strategy2_query = """
                    SELECT player_name FROM players
                    WHERE LOWER(player_name) = LOWER($1) AND guild_id = $2 AND is_active = TRUE
                """
                if log_level == 'debug':
                    logging.debug(f"[STRATEGY2] Case-insensitive player_name match: {strategy2_query}")
                    logging.debug(f"[STRATEGY2] Parameters: ({name_or_nickname}, {guild_id})")

                result = await conn.fetchrow(strategy2_query, name_or_nickname, guild_id)
                if result:
                    if log_level == 'debug':
                        logging.debug(f"[STRATEGY2] Found case-insensitive player_name match: {result[0]}")
                    return result[0]
                elif log_level == 'debug':
                    logging.debug("[STRATEGY2] No case-insensitive player_name match found")

                # Strategy 3: Exact nickname match (case-sensitive)
                strategy3_query = """
                    SELECT player_name FROM players
                    WHERE nicknames IS NOT NULL
                    AND nicknames ? $1
                    AND guild_id = $2
                    AND is_active = TRUE
                """
                if log_level == 'debug':
                    logging.debug(f"[STRATEGY3] Exact nickname match: {strategy3_query}")
                    logging.debug(f"[STRATEGY3] Parameters: ({name_or_nickname}, {guild_id})")

                result = await conn.fetchrow(strategy3_query, name_or_nickname, guild_id)
                if result:
                    if log_level == 'debug':
                        logging.debug(f"[STRATEGY3] Found exact nickname match: {result[0]}")
                    return result[0]
                elif log_level == 'debug':
                    logging.debug("[STRATEGY3] No exact nickname match found")

                # Strategy 4: Case-insensitive nickname match (Python list approach)
                if log_level == 'debug':
                    logging.debug("[STRATEGY4] Starting Python list-based nickname matching")

                nickname_results = await conn.fetch("""
                    SELECT player_name, nicknames
                    FROM players
                    WHERE guild_id = $1 AND is_active = TRUE AND nicknames IS NOT NULL
                """, guild_id)

                if log_level == 'debug':
                    logging.debug(f"[STRATEGY4] Found {len(nickname_results)} players with nicknames in guild {guild_id}")

                for row in nickname_results:
                    player_name = row[0]
                    nicknames = row[1]
                    if log_level == 'debug':
                        logging.debug(f"[STRATEGY4] Checking {player_name}: {nicknames} (type: {type(nicknames)})")

                    if isinstance(nicknames, list):
                        for nickname in nicknames:
                            if isinstance(nickname, str):
                                if log_level == 'debug':
                                    logging.debug(f"[STRATEGY4]   Testing nickname: '{nickname}' vs '{name_or_nickname}'")
                                    logging.debug(f"[STRATEGY4]   LOWER comparison: '{nickname.lower()}' == '{name_or_nickname.lower()}' => {nickname.lower() == name_or_nickname.lower()}")

                                if nickname.lower() == name_or_nickname.lower():
                                    if log_level == 'debug':
                                        logging.debug(f"[STRATEGY4] Found case-insensitive nickname match: '{nickname}' -> {player_name}")
                                    return player_name
                    elif isinstance(nicknames, dict):
                        if log_level == 'debug':
                            logging.debug(f"[STRATEGY4]   Skipping dict (empty placeholder): {nicknames}")
                        continue
                    else:
                        if log_level == 'debug':
                            logging.debug(f"[STRATEGY4]   Unexpected nickname format: {type(nicknames)}")

                if log_level == 'debug':
                    logging.debug("[STRATEGY4] No case-insensitive nickname match found")

                # Strategy 5: Alternative JSONB case-insensitive approach (fallback)
                try:
                    strategy5_query = """
                        SELECT player_name FROM players
                        WHERE guild_id = $1
                        AND is_active = TRUE
                        AND nicknames IS NOT NULL
                        AND LOWER(nicknames::text) LIKE LOWER($2)
                    """
                    if log_level == 'debug':
                        logging.debug(f"[STRATEGY5] Alternative JSONB text search: {strategy5_query}")
                        logging.debug(f"[STRATEGY5] Parameters: ({guild_id}, '%{name_or_nickname}%')")

                    result = await conn.fetchrow(strategy5_query, guild_id, f'%"{name_or_nickname}"%')
                    if result:
                        if log_level == 'debug':
                            logging.debug(f"[STRATEGY5] Found alternative JSONB match: {result[0]}")
                        return result[0]
                    elif log_level == 'debug':
                        logging.debug("[STRATEGY5] No alternative JSONB match found")

                except Exception as e:
                    if log_level == 'debug':
                        logging.debug(f"[STRATEGY5] Alternative JSONB strategy failed: {e}")

                # Strategy 6: Match display_name (Discord display name)
                strategy6_query = """
                    SELECT player_name FROM players
                    WHERE LOWER(display_name) = LOWER($1) AND guild_id = $2 AND is_active = TRUE
                """
                if log_level == 'debug':
                    logging.debug(f"[STRATEGY6] Display name match: {strategy6_query}")
                    logging.debug(f"[STRATEGY6] Parameters: ({name_or_nickname}, {guild_id})")

                result = await conn.fetchrow(strategy6_query, name_or_nickname, guild_id)
                if result:
                    if log_level == 'debug':
                        logging.debug(f"[STRATEGY6] Found display_name match: {result[0]}")
                    return result[0]
                elif log_level == 'debug':
                    logging.debug("[STRATEGY6] No display_name match found")

                # Strategy 7: Match discord_username (Discord username)
                strategy7_query = """
                    SELECT player_name FROM players
                    WHERE LOWER(discord_username) = LOWER($1) AND guild_id = $2 AND is_active = TRUE
                """
                if log_level == 'debug':
                    logging.debug(f"[STRATEGY7] Discord username match: {strategy7_query}")
                    logging.debug(f"[STRATEGY7] Parameters: ({name_or_nickname}, {guild_id})")

                result = await conn.fetchrow(strategy7_query, name_or_nickname, guild_id)
                if result:
                    if log_level == 'debug':
                        logging.debug(f"[STRATEGY7] Found discord_username match: {result[0]}")
                    return result[0]
                elif log_level == 'debug':
                    logging.debug("[STRATEGY7] No discord_username match found")

                # Final debugging: show all available data
                if log_level == 'debug':
                    all_players = await conn.fetch("""
                        SELECT player_name, nicknames
                        FROM players
                        WHERE guild_id = $1 AND is_active = TRUE
                    """, guild_id)

                    logging.debug(f"[FINAL] Resolution failed for '{name_or_nickname}' in guild {guild_id}")
                    logging.debug("[FINAL] All active players in this guild:")
                    for row in all_players:
                        logging.debug(f"[FINAL]   - {row[0]}: {row[1] if row[1] else 'No nicknames'}")

                return None  # Not found

        except Exception as e:
            if log_level == 'error':
                logging.error(f"Database error resolving player name '{name_or_nickname}' (guild: {guild_id}): {e}")
                logging.error(f"Full traceback: {traceback.format_exc()}")
            elif log_level == 'debug':
                logging.debug(f"Database lookup failed for '{name_or_nickname}' (expected if opponent): {e}")
            return None

    async def get_player_info(self, name_or_nickname: str, guild_id: int = 0) -> dict | None:
        """Get basic roster info for a player."""
        main_name = await self.resolve_player_name(name_or_nickname, guild_id)
        if not main_name:
            return None

        try:
            async with self.get_connection() as conn:
                row = await conn.fetchrow("""
                    SELECT player_name, added_by, created_at, updated_at, team, nicknames
                    FROM players WHERE player_name = $1 AND guild_id = $2 AND is_active = TRUE
                """, main_name, guild_id)

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
            logging.error(f"Error getting player info: {e}")
            return None

    async def get_all_players_stats(self, guild_id: int = 0) -> list[dict]:
        """Get all roster players info."""
        try:
            async with self.get_connection() as conn:
                rows = await conn.fetch("""
                    SELECT player_name, added_by, created_at, updated_at, team, nicknames, member_status, country_code, discord_user_id
                    FROM players
                    WHERE guild_id = $1 AND is_active = TRUE
                    ORDER BY member_status, player_name
                """, guild_id)

                results = []
                for row in rows:
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
            logging.error(f"Error getting all player stats: {e}")
            return []

    async def get_all_players_stats_global(self, limit: int | None = None) -> list[dict]:
        """Get basic stats for all active players across all guilds for global leaderboard.

        Automatically excludes testing/dev guilds configured in EXCLUDED_GUILD_IDS env var.
        """

        try:
            async with self.get_connection() as conn:
                query = """
                    SELECT player_name, guild_id, team, nicknames,
                           country_code, member_status
                    FROM players
                    WHERE is_active = TRUE
                """

                params: list = []
                param_idx = 1

                if EXCLUDED_GUILD_IDS:
                    placeholders = ','.join([f'${i}' for i in range(param_idx, param_idx + len(EXCLUDED_GUILD_IDS))])
                    query += f" AND guild_id NOT IN ({placeholders})"
                    params.extend(EXCLUDED_GUILD_IDS)
                    param_idx += len(EXCLUDED_GUILD_IDS)

                query += " ORDER BY player_name"

                if limit is not None:
                    query += f" LIMIT ${param_idx}"
                    params.append(limit)

                rows = await conn.fetch(query, *params)

                players = []
                for row in rows:
                    players.append({
                        'player_name': row[0],
                        'guild_id': row[1],
                        'team': row[2] or 'Unassigned',
                        'nicknames': row[3] or [],
                        'country_code': row[4] or None,
                        'member_status': row[5] or 'member',
                    })

                logging.info(f"Retrieved {len(players)} active players globally")
                return players

        except Exception as e:
            logging.error(f"Error getting global players: {e}")
            return []

    # Roster Management Methods

    async def get_roster_players(self, guild_id: int = 0) -> list[str]:
        """Get list of active roster players."""
        try:
            async with self.get_connection() as conn:
                rows = await conn.fetch("""
                    SELECT player_name FROM players
                    WHERE guild_id = $1 AND is_active = TRUE
                    ORDER BY player_name
                """, guild_id)

                return [row[0] for row in rows]

        except Exception as e:
            logging.error(f"Error getting roster players: {e}")
            return []

    async def add_roster_player(self, player_name: str, added_by: str = None, *, guild_id: int, member_status: str = 'member') -> bool:
        """Add a player to the active roster with optional member status."""
        self._validate_guild_id(guild_id, "add_roster_player")

        try:
            async with self.get_connection() as conn:
                existing = await conn.fetchrow("""
                    SELECT id, is_active FROM players WHERE player_name = $1 AND guild_id = $2
                """, player_name, guild_id)

                if existing:
                    if existing[1]:  # Already active
                        logging.info(f"Player {player_name} is already in the active roster")
                        return False
                    else:
                        await conn.execute("""
                            UPDATE players
                            SET is_active = TRUE, updated_at = CURRENT_TIMESTAMP, added_by = $1, member_status = $2
                            WHERE player_name = $3 AND guild_id = $4
                        """, added_by, member_status, player_name, guild_id)
                        logging.info(f"Reactivated player {player_name} in roster")
                else:
                    await conn.execute("""
                        INSERT INTO players (player_name, added_by, guild_id, member_status)
                        VALUES ($1, $2, $3, $4)
                    """, player_name, added_by, guild_id, member_status)
                    logging.info(f"Added player {player_name} to roster")

                return True

        except Exception as e:
            logging.error(f"Error adding player to roster: {e}")
            return False

    async def remove_roster_player(self, player_name: str, guild_id: int = 0) -> bool:
        """Remove a player from the active roster (mark as inactive)."""
        self._validate_guild_id(guild_id, "remove_roster_player")
        try:
            async with self.get_connection() as conn:
                existing = await conn.fetchrow("""
                    SELECT id FROM players WHERE player_name = $1 AND guild_id = $2 AND is_active = TRUE
                """, player_name, guild_id)

                if not existing:
                    logging.info(f"Player {player_name} is not in the active roster")
                    return False

                await conn.execute("""
                    UPDATE players
                    SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP
                    WHERE player_name = $1 AND guild_id = $2
                """, player_name, guild_id)

                logging.info(f"Removed player {player_name} from active roster")
                return True

        except Exception as e:
            logging.error(f"Error removing player from roster: {e}")
            return False

    # Team Assignment Methods

    async def set_player_team(self, player_name: str, team: str, guild_id: int = 0) -> bool:
        """Set a player's team assignment."""
        self._validate_guild_id(guild_id, "set_player_team")
        # Get valid teams via guild repository (accessed through db_manager)
        valid_teams = await self._db.guilds.get_guild_team_names(guild_id) + ['Unassigned']

        if team not in valid_teams:
            logging.error(f"Invalid team '{team}'. Valid teams for guild {guild_id}: {valid_teams}")
            return False

        try:
            async with self.get_connection() as conn:
                existing = await conn.fetchrow("""
                    SELECT id FROM players WHERE player_name = $1 AND guild_id = $2 AND is_active = TRUE
                """, player_name, guild_id)

                if not existing:
                    logging.error(f"Player {player_name} not found in active roster")
                    return False

                await conn.execute("""
                    UPDATE players
                    SET team = $1, updated_at = CURRENT_TIMESTAMP
                    WHERE player_name = $2 AND guild_id = $3 AND is_active = TRUE
                """, team, player_name, guild_id)

                logging.info(f"Set {player_name}'s team to {team}")
                return True

        except Exception as e:
            logging.error(f"Error setting player team: {e}")
            return False

    async def get_players_by_team(self, team: str | None = None, guild_id: int = 0) -> dict[str, list[str]]:
        """Get players organized by team, or players from a specific team."""
        self._validate_guild_id(guild_id, "get_players_by_team")
        try:
            async with self.get_connection() as conn:
                if team:
                    rows = await conn.fetch("""
                        SELECT player_name FROM players
                        WHERE team = $1 AND guild_id = $2 AND is_active = TRUE
                        ORDER BY player_name
                    """, team, guild_id)

                    return {team: [row[0] for row in rows]}
                else:
                    rows = await conn.fetch("""
                        SELECT team, player_name FROM players
                        WHERE guild_id = $1 AND is_active = TRUE
                        ORDER BY team, player_name
                    """, guild_id)

                    teams = {}
                    for row in rows:
                        team_name, player_name = row[0], row[1]
                        if team_name not in teams:
                            teams[team_name] = []
                        teams[team_name].append(player_name)

                    return teams

        except Exception as e:
            logging.error(f"Error getting players by team: {e}")
            return {}

    async def get_team_roster(self, team: str, guild_id: int = 0) -> list[str]:
        """Get list of players in a specific team."""
        team_data = await self.get_players_by_team(team, guild_id)
        return team_data.get(team, [])

    async def get_player_team(self, player_name: str, guild_id: int = 0) -> str | None:
        """Get a player's current team assignment."""
        try:
            async with self.get_connection() as conn:
                result = await conn.fetchrow("""
                    SELECT team FROM players
                    WHERE player_name = $1 AND guild_id = $2 AND is_active = TRUE
                """, player_name, guild_id)

                return result[0] if result else None

        except Exception as e:
            logging.error(f"Error getting player team: {e}")
            return None

    # Nickname Management Methods

    async def add_nickname(self, player_name: str, nickname: str, guild_id: int = 0) -> bool:
        """Add a nickname to a player's nickname list."""
        self._validate_guild_id(guild_id, "add_nickname")
        try:
            async with self.get_connection() as conn:
                result = await conn.fetchrow("""
                    SELECT nicknames FROM players
                    WHERE player_name = $1 AND guild_id = $2 AND is_active = TRUE
                """, player_name, guild_id)

                if not result:
                    logging.error(f"Player {player_name} not found in active roster")
                    return False

                current_nicknames = result[0] if result[0] else []

                if nickname in current_nicknames:
                    logging.info(f"Nickname '{nickname}' already exists for {player_name}")
                    return False

                updated_nicknames = current_nicknames + [nickname]

                await conn.execute("""
                    UPDATE players
                    SET nicknames = $1, updated_at = CURRENT_TIMESTAMP
                    WHERE player_name = $2 AND guild_id = $3 AND is_active = TRUE
                """, updated_nicknames, player_name, guild_id)

                logging.info(f"Added nickname '{nickname}' to {player_name}")
                return True

        except Exception as e:
            logging.error(f"Error adding nickname: {e}")
            return False

    async def remove_nickname(self, player_name: str, nickname: str, guild_id: int = 0) -> bool:
        """Remove a nickname from a player's nickname list."""
        self._validate_guild_id(guild_id, "remove_nickname")
        try:
            async with self.get_connection() as conn:
                result = await conn.fetchrow("""
                    SELECT nicknames FROM players
                    WHERE player_name = $1 AND guild_id = $2 AND is_active = TRUE
                """, player_name, guild_id)

                if not result:
                    logging.error(f"Player {player_name} not found in active roster")
                    return False

                current_nicknames = result[0] if result[0] else []

                if nickname not in current_nicknames:
                    logging.info(f"Nickname '{nickname}' not found for {player_name}")
                    return False

                updated_nicknames = [n for n in current_nicknames if n != nickname]

                await conn.execute("""
                    UPDATE players
                    SET nicknames = $1, updated_at = CURRENT_TIMESTAMP
                    WHERE player_name = $2 AND guild_id = $3 AND is_active = TRUE
                """, updated_nicknames, player_name, guild_id)

                logging.info(f"Removed nickname '{nickname}' from {player_name}")
                return True

        except Exception as e:
            logging.error(f"Error removing nickname: {e}")
            return False

    async def get_player_nicknames(self, player_name: str, guild_id: int = 0) -> list[str]:
        """Get all nicknames for a player."""
        self._validate_guild_id(guild_id, "get_player_nicknames")
        try:
            async with self.get_connection() as conn:
                result = await conn.fetchrow("""
                    SELECT nicknames FROM players
                    WHERE player_name = $1 AND guild_id = $2 AND is_active = TRUE
                """, player_name, guild_id)

                return result[0] if result and result[0] else []

        except Exception as e:
            logging.error(f"Error getting player nicknames: {e}")
            return []

    async def set_player_nicknames(self, player_name: str, nicknames: list[str], guild_id: int = 0) -> bool:
        """Set all nicknames for a player (replaces existing nicknames)."""
        self._validate_guild_id(guild_id, "set_player_nicknames")
        try:
            async with self.get_connection() as conn:
                existing = await conn.fetchrow("""
                    SELECT id FROM players WHERE player_name = $1 AND guild_id = $2 AND is_active = TRUE
                """, player_name, guild_id)

                if not existing:
                    logging.error(f"Player {player_name} not found in active roster")
                    return False

                unique_nicknames = []
                for nickname in nicknames:
                    if nickname not in unique_nicknames:
                        unique_nicknames.append(nickname)

                await conn.execute("""
                    UPDATE players
                    SET nicknames = $1, updated_at = CURRENT_TIMESTAMP
                    WHERE player_name = $2 AND guild_id = $3 AND is_active = TRUE
                """, unique_nicknames, player_name, guild_id)

                logging.info(f"Set nicknames for {player_name}: {unique_nicknames}")
                return True

        except Exception as e:
            logging.error(f"Error setting player nicknames: {e}")
            return False

    # Member Status Methods

    async def set_player_member_status(self, player_name: str, member_status: str, guild_id: int = 0) -> bool:
        """Set the member status for a player."""
        self._validate_guild_id(guild_id, "set_player_member_status")
        try:
            async with self.get_connection() as conn:
                resolved_player = await self.resolve_player_name(player_name, guild_id)
                if not resolved_player:
                    logging.error(f"Player {player_name} not found in guild {guild_id}")
                    return False

                status = await conn.execute("""
                    UPDATE players
                    SET member_status = $1, updated_at = CURRENT_TIMESTAMP
                    WHERE player_name = $2 AND guild_id = $3 AND is_active = TRUE
                """, member_status, resolved_player, guild_id)

                rows_affected = int(status.split()[-1])
                if rows_affected == 0:
                    logging.error(f"No active player {resolved_player} found to update")
                    return False

                logging.info(f"Updated {resolved_player} member status to {member_status}")
                return True

        except Exception as e:
            logging.error(f"Error setting member status: {e}")
            return False

    async def get_players_by_member_status(self, member_status: str, guild_id: int = 0) -> list[dict]:
        """Get all players with a specific member status."""
        self._validate_guild_id(guild_id, "get_players_by_member_status")
        try:
            async with self.get_connection() as conn:
                rows = await conn.fetch("""
                    SELECT player_name, team, nicknames, created_at, updated_at
                    FROM players
                    WHERE member_status = $1 AND guild_id = $2 AND is_active = TRUE
                    ORDER BY player_name
                """, member_status, guild_id)

                players = []
                for row in rows:
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
            logging.error(f"Error getting players by member status: {e}")
            return []

    async def get_member_status_counts(self, guild_id: int = 0) -> dict[str, int]:
        """Get count of players by member status."""
        self._validate_guild_id(guild_id, "get_member_status_counts")
        try:
            async with self.get_connection() as conn:
                rows = await conn.fetch("""
                    SELECT member_status, COUNT(*)
                    FROM players
                    WHERE guild_id = $1 AND is_active = TRUE
                    GROUP BY member_status
                """, guild_id)

                return {row[0]: row[1] for row in rows}

        except Exception as e:
            logging.error(f"Error getting member status counts: {e}")
            return {}

    # Discord User ID Support Methods

    async def add_roster_player_with_discord(
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
            async with self.get_connection() as conn:
                existing = await conn.fetchrow("""
                    SELECT id, is_active, player_name FROM players
                    WHERE discord_user_id = $1 AND guild_id = $2
                """, discord_user_id, guild_id)

                if existing:
                    if existing[1]:  # Already active
                        logging.info(f"Player with Discord ID {discord_user_id} is already in the active roster as {existing[2]}")
                        return False
                    else:
                        await conn.execute("""
                            UPDATE players
                            SET is_active = TRUE,
                                player_name = $1,
                                display_name = $2,
                                discord_username = $3,
                                member_status = $4,
                                country_code = $5,
                                updated_at = CURRENT_TIMESTAMP,
                                added_by = $6,
                                last_role_sync = CURRENT_TIMESTAMP
                            WHERE discord_user_id = $7 AND guild_id = $8
                        """, player_name, display_name, discord_username, member_status, country_code, added_by, discord_user_id, guild_id)
                        logging.info(f"Reactivated player {player_name} (Discord ID: {discord_user_id})")
                else:
                    await conn.execute("""
                        INSERT INTO players (
                            discord_user_id, player_name, display_name, discord_username,
                            member_status, added_by, guild_id, country_code, last_role_sync
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, CURRENT_TIMESTAMP)
                    """, discord_user_id, player_name, display_name, discord_username, member_status, added_by, guild_id, country_code)
                    logging.info(f"Added player {player_name} with Discord ID {discord_user_id}")

                return True

        except Exception as e:
            logging.error(f"Error adding player with Discord ID to roster: {e}")
            return False

    async def link_player_to_discord_user(
        self,
        player_name: str,
        discord_user_id: int,
        display_name: str,
        discord_username: str,
        member_status: str,
        guild_id: int = 0
    ) -> bool:
        """Link an existing player to a Discord user."""
        self._validate_guild_id(guild_id, "link_player_to_discord_user")
        try:
            async with self.get_connection() as conn:
                result = await conn.fetchrow("""
                    SELECT id, discord_user_id FROM players
                    WHERE player_name = $1 AND guild_id = $2 AND is_active = TRUE
                """, player_name, guild_id)

                if not result:
                    logging.error(f"Player {player_name} not found in active roster")
                    return False

                if result[1] is not None:
                    logging.warning(f"Player {player_name} is already linked to Discord ID {result[1]}")
                    return False

                await conn.execute("""
                    UPDATE players
                    SET discord_user_id = $1,
                        display_name = $2,
                        discord_username = $3,
                        member_status = $4,
                        last_role_sync = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE player_name = $5 AND guild_id = $6
                """, discord_user_id, display_name, discord_username, member_status, player_name, guild_id)

                logging.info(f"Linked player {player_name} to Discord ID {discord_user_id}")
                return True

        except Exception as e:
            logging.error(f"Error linking player to Discord user: {e}")
            return False

    async def sync_player_discord_info(
        self,
        discord_user_id: int,
        display_name: str,
        discord_username: str,
        guild_id: int = 0
    ) -> bool:
        """Sync player's display name and Discord username from Discord."""
        self._validate_guild_id(guild_id, "sync_player_discord_info")
        try:
            async with self.get_connection() as conn:
                status = await conn.execute("""
                    UPDATE players
                    SET display_name = $1,
                        discord_username = $2,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE discord_user_id = $3 AND guild_id = $4
                """, display_name, discord_username, discord_user_id, guild_id)

                rows_affected = int(status.split()[-1])
                if rows_affected > 0:
                    logging.debug(f"Synced Discord info for user {discord_user_id}")
                    return True
                else:
                    logging.debug(f"No player found with Discord ID {discord_user_id} in guild {guild_id}")
                    return False

        except Exception as e:
            logging.error(f"Error syncing player Discord info: {e}")
            return False

    async def sync_player_role(
        self,
        discord_user_id: int,
        member_status: str,
        guild_id: int = 0
    ) -> bool:
        """Sync player's member_status from their Discord role."""
        self._validate_guild_id(guild_id, "sync_player_role")
        try:
            async with self.get_connection() as conn:
                status = await conn.execute("""
                    UPDATE players
                    SET member_status = $1,
                        last_role_sync = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE discord_user_id = $2 AND guild_id = $3
                """, member_status, discord_user_id, guild_id)

                rows_affected = int(status.split()[-1])
                if rows_affected > 0:
                    logging.debug(f"Synced role for Discord user {discord_user_id} to {member_status}")
                    return True
                else:
                    logging.debug(f"No player found with Discord ID {discord_user_id} in guild {guild_id}")
                    return False

        except Exception as e:
            logging.error(f"Error syncing player role: {e}")
            return False

    async def get_unlinked_players(self, guild_id: int = 0) -> list[dict]:
        """Get all active players without a Discord user ID link."""
        self._validate_guild_id(guild_id, "get_unlinked_players")
        try:
            async with self.get_connection() as conn:
                rows = await conn.fetch("""
                    SELECT player_name, team, member_status, total_score, war_count
                    FROM players
                    WHERE discord_user_id IS NULL
                    AND is_active = TRUE
                    AND guild_id = $1
                    ORDER BY player_name
                """, guild_id)

                players = []
                for row in rows:
                    players.append({
                        'player_name': row[0],
                        'team': row[1],
                        'member_status': row[2],
                        'total_score': row[3],
                        'war_count': float(row[4]) if row[4] else 0
                    })

                return players

        except Exception as e:
            logging.error(f"Error getting unlinked players: {e}")
            return []

    async def get_player_name_by_discord_id(self, discord_user_id: int, guild_id: int) -> str | None:
        """Return the player_name for an active player linked to a Discord user, or None."""
        self._validate_guild_id(guild_id, "get_player_name_by_discord_id")
        try:
            async with self.get_connection() as conn:
                result = await conn.fetchrow("""
                    SELECT player_name
                    FROM players
                    WHERE discord_user_id = $1 AND guild_id = $2 AND is_active = TRUE
                """, discord_user_id, guild_id)
                return result[0] if result else None

        except Exception as e:
            logging.error(f"Error getting player name by Discord ID: {e}")
            return None

    # Country Code Methods

    async def set_country_code(self, player_name: str, country_code: str | None, guild_id: int) -> bool:
        """Set the country code for a player by player_name.

        Args:
            player_name: The player's name (case-insensitive match)
            country_code: 2-letter country code or None to clear
            guild_id: Guild ID for data isolation

        Returns:
            True if a player was updated, False otherwise
        """
        self._validate_guild_id(guild_id, "set_country_code")
        try:
            async with self.get_connection() as conn:
                status = await conn.execute("""
                    UPDATE players
                    SET country_code = $1, updated_at = CURRENT_TIMESTAMP
                    WHERE LOWER(player_name) = LOWER($2) AND guild_id = $3 AND is_active = TRUE
                """, country_code, player_name, guild_id)

                rows_affected = int(status.split()[-1])
                return rows_affected > 0

        except Exception as e:
            logging.error(f"Error setting country code for {player_name}: {e}")
            return False

    async def bulk_set_country_codes(self, updates: list[tuple[str, str]], guild_id: int) -> int:
        """Set country codes for multiple players in a single transaction.

        Args:
            updates: List of (player_name, country_code) tuples
            guild_id: Guild ID for data isolation

        Returns:
            Number of players successfully updated
        """
        self._validate_guild_id(guild_id, "bulk_set_country_codes")
        total_updated = 0
        try:
            async with self.get_connection() as conn:
                async with conn.transaction():
                    for player_name, country_code in updates:
                        status = await conn.execute("""
                            UPDATE players
                            SET country_code = $1, updated_at = CURRENT_TIMESTAMP
                            WHERE LOWER(player_name) = LOWER($2) AND guild_id = $3 AND is_active = TRUE
                        """, country_code, player_name, guild_id)

                        rows_affected = int(status.split()[-1])
                        total_updated += rows_affected

            return total_updated

        except Exception as e:
            logging.error(f"Error bulk setting country codes: {e}")
            return 0

    async def set_country_code_by_discord_id(self, discord_user_id: int, country_code: str | None, guild_id: int) -> bool:
        """Set the country code for a player by their Discord user ID.

        Args:
            discord_user_id: The player's Discord user ID
            country_code: 2-letter country code or None to clear
            guild_id: Guild ID for data isolation

        Returns:
            True if a player was updated, False otherwise
        """
        self._validate_guild_id(guild_id, "set_country_code_by_discord_id")
        try:
            async with self.get_connection() as conn:
                status = await conn.execute("""
                    UPDATE players
                    SET country_code = $1, updated_at = CURRENT_TIMESTAMP
                    WHERE discord_user_id = $2 AND guild_id = $3 AND is_active = TRUE
                """, country_code, discord_user_id, guild_id)

                rows_affected = int(status.split()[-1])
                return rows_affected > 0

        except Exception as e:
            logging.error(f"Error setting country code by Discord ID {discord_user_id}: {e}")
            return False
