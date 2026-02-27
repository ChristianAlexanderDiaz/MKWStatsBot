"""
War repository: CRUD operations for wars, duplicate detection.
"""

import json
import logging
from typing import List, Dict, Optional
from datetime import datetime, timezone, timedelta

from .base import BaseRepository


class WarRepository(BaseRepository):
    """Handles all war-related database operations."""

    def add_race_results(self, results: List[Dict], race_count: int = 12, *, guild_id: int) -> Optional[int]:
        """
        Add race results for multiple players.
        results: [{'name': 'PlayerName', 'score': 85}, ...]
        race_count: number of races in this session (default 12)
        Returns: war_id if successful, None if failed
        """
        self._validate_guild_id(guild_id, "add_race_results")

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                session_data = {
                    'race_count': race_count,
                    'results': results,
                    'timestamp': datetime.now().isoformat()
                }

                # Use Eastern Time instead of UTC
                import zoneinfo
                try:
                    eastern_tz = zoneinfo.ZoneInfo('America/New_York')
                    eastern_now = datetime.now(eastern_tz)
                except ImportError:
                    eastern_tz = timezone(timedelta(hours=-5))
                    eastern_now = datetime.now(eastern_tz)

                # Calculate team score and differential
                team_score = sum(result.get('score', 0) for result in results)
                total_points = 82 * race_count
                opponent_score = total_points - team_score
                team_differential = team_score - opponent_score

                cursor.execute("""
                    INSERT INTO wars (war_date, race_count, players_data, guild_id, team_score, team_differential)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    eastern_now.date(),
                    race_count,
                    json.dumps(session_data),
                    guild_id,
                    team_score,
                    team_differential
                ))

                war_id = cursor.fetchone()[0]

                # Insert into player_war_performances table for optimized queries
                performances_added = 0
                for result in results:
                    player_name = result.get('name')
                    resolved_name = self._db.players.resolve_player_name(player_name, guild_id, log_level='none')

                    if resolved_name:
                        cursor.execute("""
                            SELECT id FROM players
                            WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                        """, (resolved_name, guild_id))

                        player_row = cursor.fetchone()
                        if player_row:
                            player_id = player_row[0]
                            score = result.get('score', 0)
                            races_played = result.get('races', result.get('races_played', race_count))
                            war_participation = result.get('war_participation', races_played / race_count if race_count > 0 else 1.0)

                            cursor.execute("""
                                INSERT INTO player_war_performances
                                (player_id, war_id, score, races_played, war_participation)
                                VALUES (%s, %s, %s, %s, %s)
                                ON CONFLICT (player_id, war_id) DO NOTHING
                            """, (player_id, war_id, score, races_played, war_participation))
                            performances_added += 1

                conn.commit()
                logging.info(f"✅ Added war results for {len(results)} players (war ID: {war_id}, {performances_added} performances tracked)")
                return war_id

        except Exception as e:
            logging.error(f"❌ Error adding race results: {e}")
            return None

    def get_war_by_id(self, war_id: int, guild_id: int = 0) -> Optional[Dict]:
        """Get specific war details by ID."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT id, war_date, race_count, players_data, created_at, team_score, team_differential
                    FROM wars WHERE id = %s AND guild_id = %s
                """, (war_id, guild_id))

                result = cursor.fetchone()
                if not result:
                    return None

                session_data = result[3] if result[3] else {}
                return {
                    'id': result[0],
                    'war_date': result[1].isoformat() if result[1] else None,
                    'race_count': result[2],
                    'results': session_data.get('results', []),
                    'created_at': result[4].isoformat() if result[4] else None,
                    'team_score': result[5],
                    'team_differential': result[6]
                }

        except Exception as e:
            logging.error(f"❌ Error getting war by ID: {e}")
            return None

    def get_all_wars(self, limit: int = None, guild_id: int = 0) -> List[Dict]:
        """Get all wars in the database."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                query = """
                    SELECT id, war_date, race_count, players_data, created_at
                    FROM wars
                    WHERE guild_id = %s
                    ORDER BY created_at DESC
                """

                if limit:
                    query += " LIMIT %s"
                    cursor.execute(query, (guild_id, limit))
                else:
                    cursor.execute(query, (guild_id,))

                results = []
                for row in cursor.fetchall():
                    session_data = row[3] if row[3] else {}
                    player_count = len(session_data.get('results', []))

                    results.append({
                        'id': row[0],
                        'war_date': row[1].isoformat() if row[1] else None,
                        'race_count': row[2],
                        'player_count': player_count,
                        'results': session_data.get('results', []),
                        'created_at': row[4].isoformat() if row[4] else None
                    })

                # Reverse so oldest wars appear first
                return list(reversed(results))

        except Exception as e:
            logging.error(f"❌ Error getting all wars: {e}")
            return []

    def get_last_war_for_duplicate_check(self, guild_id: int = 0) -> Optional[List[Dict]]:
        """
        Get the most recent war's player results for duplicate detection.
        Returns normalized player data for comparison.
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT players_data
                    FROM wars
                    WHERE guild_id = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (guild_id,))

                result = cursor.fetchone()
                if not result or not result[0]:
                    return None

                war_data = result[0]
                player_results = war_data.get('results', [])

                if not player_results:
                    return None

                normalized_results = []
                for player in player_results:
                    normalized_results.append({
                        'name': player.get('name', '').strip().lower(),
                        'score': player.get('score', 0)
                    })

                normalized_results.sort(key=lambda x: x['name'])

                logging.info(f"✅ Retrieved last war data for duplicate check: {len(normalized_results)} players")
                return normalized_results

        except Exception as e:
            logging.error(f"❌ Error getting last war for duplicate check: {e}")
            return None

    @staticmethod
    def check_for_duplicate_war(new_results: List[Dict], last_war_results: Optional[List[Dict]]) -> bool:
        """
        Check if new war results are identical to the last war.
        Compares normalized player names and scores.
        """
        if not last_war_results or not new_results:
            return False

        normalized_new = []
        for player in new_results:
            normalized_new.append({
                'name': player.get('name', '').strip().lower(),
                'score': player.get('score', 0)
            })

        normalized_new.sort(key=lambda x: x['name'])

        if len(normalized_new) != len(last_war_results):
            return False

        for new_player, last_player in zip(normalized_new, last_war_results):
            if (new_player['name'] != last_player['name'] or
                new_player['score'] != last_player['score']):
                return False

        logging.info(f"🔍 Duplicate war detected: {len(normalized_new)} players with identical names and scores")
        return True

    def remove_war_by_id(self, war_id: int, *, guild_id: int) -> Optional[int]:
        """Remove a war by ID and update player statistics."""
        self._validate_guild_id(guild_id, "remove_war_by_id")

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                war = self.get_war_by_id(war_id, guild_id)
                if not war:
                    logging.warning(f"War ID {war_id} not found")
                    return False

                players_data = war.get('results', [])
                team_differential = war.get('team_differential', 0)
                logging.info(f"🔍 War data retrieved: {war}")
                logging.info(f"🔍 Players data from war: {players_data}")
                logging.info(f"🔍 Number of players to process: {len(players_data)}")
                logging.info(f"🔍 Team differential to remove: {team_differential}")

                stats_reverted = 0
                for i, result in enumerate(players_data):
                    logging.info(f"🔍 Processing player {i+1}/{len(players_data)}: {result}")
                    player_name = result.get('name')
                    score = result.get('score', 0)
                    races_played = result.get('races_played', war.get('race_count', 12))
                    war_participation = result.get('war_participation', 1.0)

                    if not player_name:
                        continue

                    resolved_player = self._db.players.resolve_player_name(player_name, guild_id)
                    if resolved_player:
                        success = self._db.stats.remove_player_stats_with_participation(
                            resolved_player, score, races_played, war_participation, guild_id, team_differential
                        )
                        if success:
                            stats_reverted += 1
                            logging.info(f"✅ Reverted stats for {resolved_player}: -{score} points, -{races_played} races, -{war_participation} participation")
                        else:
                            logging.warning(f"❌ Failed to revert stats for {resolved_player}")
                    else:
                        logging.warning(f"❌ Could not resolve player name: {player_name}")

                cursor.execute("DELETE FROM wars WHERE id = %s AND guild_id = %s", (war_id, guild_id))

                conn.commit()
                logging.info(f"✅ Removed war ID {war_id} and reverted stats for {stats_reverted} players")
                return stats_reverted

        except Exception as e:
            logging.error(f"❌ Error removing war: {e}")
            return None

    def append_players_to_war_by_id(self, war_id: int, new_players: List[Dict], *, guild_id: int) -> bool:
        """Append new players to an existing war without modifying existing players."""
        self._validate_guild_id(guild_id, "append_players_to_war_by_id")

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                existing_war = self.get_war_by_id(war_id, guild_id)
                if not existing_war:
                    logging.error(f"No war found with ID {war_id} in guild {guild_id}")
                    return False

                existing_results = existing_war.get('results', [])
                existing_names = {player.get('name', '').lower() for player in existing_results}

                conflicts = []
                for new_player in new_players:
                    if new_player.get('name', '').lower() in existing_names:
                        conflicts.append(new_player.get('name', 'Unknown'))

                if conflicts:
                    logging.error(f"Players already exist in war {war_id}: {', '.join(conflicts)}")
                    return False

                combined_results = existing_results + new_players

                new_team_score = sum(p.get('score', 0) for p in combined_results)
                race_count = existing_war.get('race_count', 12)
                total_points = 82 * race_count
                opponent_score = total_points - new_team_score
                new_team_differential = new_team_score - opponent_score

                war_data = {
                    "results": combined_results,
                    "timestamp": datetime.now().isoformat(),
                    "race_count": race_count
                }

                cursor.execute("""
                    UPDATE wars
                    SET players_data = %s, team_score = %s, team_differential = %s
                    WHERE id = %s AND guild_id = %s
                """, (json.dumps(war_data), new_team_score, new_team_differential, war_id, guild_id))

                if cursor.rowcount == 0:
                    logging.error(f"No war found with ID {war_id} in guild {guild_id}")
                    return False

                conn.commit()
                logging.info(f"✅ Appended {len(new_players)} players to war {war_id}, new differential: {new_team_differential:+d}")
                return True

        except Exception as e:
            logging.error(f"❌ Error appending players to war by ID: {e}")
            return False

    def update_war_by_id(self, war_id: int, results: List[Dict], race_count: int, *, guild_id: int) -> bool:
        """Update an existing war with new player data."""
        self._validate_guild_id(guild_id, "update_war_by_id")

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                war_data = {
                    "results": results,
                    "timestamp": datetime.now().isoformat(),
                    "race_count": race_count
                }

                cursor.execute("""
                    UPDATE wars
                    SET players_data = %s, race_count = %s
                    WHERE id = %s AND guild_id = %s
                """, (json.dumps(war_data), race_count, war_id, guild_id))

                if cursor.rowcount == 0:
                    logging.error(f"No war found with ID {war_id} in guild {guild_id}")
                    return False

                conn.commit()
                logging.info(f"✅ Updated war {war_id} with {len(results)} players")
                return True

        except Exception as e:
            logging.error(f"❌ Error updating war by ID: {e}")
            return False
