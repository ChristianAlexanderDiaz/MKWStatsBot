"""
Stats repository: Player statistics, metrics calculation, and caching.
"""

import logging
import statistics
from typing import List, Dict, Optional

from .base import BaseRepository
from ..constants import (
    FORM_SCORE_DECAY_FACTOR,
    FORM_SCORE_MIN_WARS,
    CLOSE_WAR_THRESHOLD,
    CLUTCH_ELITE_THRESHOLD,
    CLUTCH_POSITIVE_THRESHOLD,
    CLUTCH_NEUTRAL_THRESHOLD,
    CLUTCH_SHAKY_THRESHOLD,
)


class StatsRepository(BaseRepository):
    """Handles all player statistics and metrics operations."""

    def update_player_stats(self, player_name: str, score: int, races_played: int, war_participation: float, war_date: str, guild_id: int = 0, team_differential: int = 0) -> bool:
        """Update player statistics when a war is added with fractional war support.

        Also updates stable metrics and invalidates volatile metrics for cache.
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT id, total_score, total_races, war_count, total_team_differential
                    FROM players WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (player_name, guild_id))

                result = cursor.fetchone()
                if result:
                    player_id = result[0]
                    new_total_score = result[1] + score
                    new_total_races = result[2] + races_played
                    new_war_count = float(result[3]) + war_participation
                    scaled_differential = int(team_differential * war_participation)
                    new_total_differential = (result[4] or 0) + scaled_differential
                    new_average = round(new_total_score / new_war_count, 2)

                    cursor.execute("""
                        UPDATE players
                        SET total_score = %s, total_races = %s, war_count = %s,
                            average_score = %s, last_war_date = %s, total_team_differential = %s,
                            -- Recalculate stable metrics via subqueries
                            score_stddev = COALESCE((
                                SELECT STDDEV_POP(score) FROM player_war_performances
                                WHERE player_id = %s
                            ), 0.0),
                            highest_score = COALESCE((
                                SELECT MAX(score) FROM player_war_performances
                                WHERE player_id = %s AND races_played = 12
                            ), 0),
                            lowest_score = COALESCE((
                                SELECT MIN(score) FROM player_war_performances
                                WHERE player_id = %s AND races_played = 12
                            ), 0),
                            wins = COALESCE((
                                SELECT COUNT(*) FROM player_war_performances pwp
                                JOIN wars w ON pwp.war_id = w.id
                                WHERE pwp.player_id = %s AND w.team_differential > 0 AND w.guild_id = %s
                            ), 0),
                            losses = COALESCE((
                                SELECT COUNT(*) FROM player_war_performances pwp
                                JOIN wars w ON pwp.war_id = w.id
                                WHERE pwp.player_id = %s AND w.team_differential < 0 AND w.guild_id = %s
                            ), 0),
                            ties = COALESCE((
                                SELECT COUNT(*) FROM player_war_performances pwp
                                JOIN wars w ON pwp.war_id = w.id
                                WHERE pwp.player_id = %s AND w.team_differential = 0 AND w.guild_id = %s
                            ), 0),
                            consistency_score = CASE
                                WHEN %s >= 2 AND %s > 0
                                THEN GREATEST(0, 100 - (
                                    COALESCE((
                                        SELECT STDDEV_POP(score) FROM player_war_performances
                                        WHERE player_id = %s
                                    ), 0.0) / %s * 100
                                ))
                                ELSE NULL
                            END,
                            win_percentage = CASE
                                WHEN %s > 0
                                THEN (COALESCE((
                                    SELECT COUNT(*) FROM player_war_performances pwp
                                    JOIN wars w ON pwp.war_id = w.id
                                    WHERE pwp.player_id = %s AND w.team_differential > 0 AND w.guild_id = %s
                                ), 0)::DECIMAL / %s * 100)
                                ELSE 0.0
                            END,
                            -- Invalidate volatile metrics (set to NULL)
                            avg10_score = NULL,
                            form_score = NULL,
                            clutch_factor = NULL,
                            potential = NULL,
                            hotstreak = NULL,
                            cached_metrics_updated_at = NULL,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE player_name = %s AND guild_id = %s
                    """, (new_total_score, new_total_races, new_war_count, new_average, war_date, new_total_differential,
                          player_id, player_id, player_id, player_id, guild_id, player_id, guild_id, player_id, guild_id,
                          new_war_count, new_average, player_id, new_average,
                          new_war_count, player_id, guild_id, new_war_count,
                          player_name, guild_id))
                else:
                    logging.error(f"Player {player_name} not found in players table for guild {guild_id}")
                    return False

                conn.commit()
                logging.info(f"✅ Updated stats for {player_name}: +{score} points, +{races_played} races, +{war_participation} wars, differential: {team_differential:+d}")
                return True

        except Exception as e:
            logging.error(f"❌ Error updating player stats: {e}")
            return False

    def remove_player_stats_with_participation(self, player_name: str, score: int, races_played: int, war_participation: float, guild_id: int = 0, team_differential: int = 0) -> bool:
        """Remove player statistics when a war is removed, accounting for war participation."""
        logging.info(f"🔍 Attempting to remove stats for player: {player_name}, guild_id: {guild_id}")
        logging.info(f"    Score to remove: {score}, Races: {races_played}, War participation: {war_participation}, Differential: {team_differential}")

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                logging.info(f"🔍 Querying for player: {player_name} in guild {guild_id}")
                cursor.execute("""
                    SELECT total_score, total_races, war_count, total_team_differential
                    FROM players WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (player_name, guild_id))

                result = cursor.fetchone()
                if not result:
                    logging.warning(f"❌ No stats found for {player_name} in guild {guild_id} (or player inactive)")

                    cursor.execute("SELECT player_name, guild_id, is_active FROM players WHERE player_name = %s", (player_name,))
                    all_matches = cursor.fetchall()
                    if all_matches:
                        logging.warning(f"🔍 Player '{player_name}' exists but in different states: {all_matches}")
                    else:
                        logging.warning(f"🔍 Player '{player_name}' does not exist in players table at all")
                    return False

                current_total_score, current_total_races, current_war_count, current_total_differential = result
                logging.info(f"✅ Found player {player_name}: current stats = {current_total_score} points, {current_total_races} races, {current_war_count} wars, differential: {current_total_differential}")

                current_war_count = float(current_war_count)

                new_total_score = max(0, current_total_score - score)
                new_total_races = max(0, current_total_races - races_played)
                new_war_count = max(0.0, current_war_count - war_participation)
                scaled_differential = int(team_differential * war_participation)
                new_total_differential = (current_total_differential or 0) - scaled_differential

                logging.info(f"🔍 Calculated new stats: {new_total_score} points, {new_total_races} races, {new_war_count} wars, differential: {new_total_differential}")

                if new_war_count > 0:
                    new_average = round(new_total_score / new_war_count, 2)
                else:
                    new_average = 0.0

                logging.info(f"🔍 New average score: {new_average}")

                cursor.execute("""
                    SELECT id FROM players
                    WHERE player_name = %s AND guild_id = %s
                """, (player_name, guild_id))

                player_row = cursor.fetchone()
                if not player_row:
                    logging.error(f"Could not get player ID for {player_name}")
                    return False

                player_id = player_row[0]

                logging.info(f"🔍 Executing UPDATE for player {player_name}")
                cursor.execute("""
                    UPDATE players
                    SET total_score = %s, total_races = %s, war_count = %s,
                        average_score = %s, total_team_differential = %s,
                        -- Recalculate stable metrics via subqueries
                        score_stddev = COALESCE((
                            SELECT STDDEV_POP(score) FROM player_war_performances
                            WHERE player_id = %s
                        ), 0.0),
                        highest_score = COALESCE((
                            SELECT MAX(score) FROM player_war_performances
                            WHERE player_id = %s AND races_played = 12
                        ), 0),
                        lowest_score = COALESCE((
                            SELECT MIN(score) FROM player_war_performances
                            WHERE player_id = %s AND races_played = 12
                        ), 0),
                        wins = COALESCE((
                            SELECT COUNT(*) FROM player_war_performances pwp
                            JOIN wars w ON pwp.war_id = w.id
                            WHERE pwp.player_id = %s AND w.team_differential > 0 AND w.guild_id = %s
                        ), 0),
                        losses = COALESCE((
                            SELECT COUNT(*) FROM player_war_performances pwp
                            JOIN wars w ON pwp.war_id = w.id
                            WHERE pwp.player_id = %s AND w.team_differential < 0 AND w.guild_id = %s
                        ), 0),
                        ties = COALESCE((
                            SELECT COUNT(*) FROM player_war_performances pwp
                            JOIN wars w ON pwp.war_id = w.id
                            WHERE pwp.player_id = %s AND w.team_differential = 0 AND w.guild_id = %s
                        ), 0),
                        consistency_score = CASE
                            WHEN %s >= 2 AND %s > 0
                            THEN GREATEST(0, 100 - (
                                COALESCE((
                                    SELECT STDDEV_POP(score) FROM player_war_performances
                                    WHERE player_id = %s
                                ), 0.0) / %s * 100
                            ))
                            ELSE NULL
                        END,
                        win_percentage = CASE
                            WHEN %s > 0
                            THEN (COALESCE((
                                SELECT COUNT(*) FROM player_war_performances pwp
                                JOIN wars w ON pwp.war_id = w.id
                                WHERE pwp.player_id = %s AND w.team_differential > 0 AND w.guild_id = %s
                            ), 0)::DECIMAL / %s * 100)
                            ELSE 0.0
                        END,
                        -- Invalidate volatile metrics (set to NULL)
                        avg10_score = NULL,
                        form_score = NULL,
                        clutch_factor = NULL,
                        potential = NULL,
                        hotstreak = NULL,
                        cached_metrics_updated_at = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE player_name = %s AND guild_id = %s
                """, (new_total_score, new_total_races, new_war_count, new_average, new_total_differential,
                      player_id, player_id, player_id, player_id, guild_id, player_id, guild_id, player_id, guild_id,
                      new_war_count, new_average, player_id, new_average,
                      new_war_count, player_id, guild_id, new_war_count,
                      player_name, guild_id))

                rows_affected = cursor.rowcount
                logging.info(f"🔍 UPDATE affected {rows_affected} rows")

                if rows_affected == 0:
                    logging.warning(f"❌ UPDATE statement affected 0 rows for player {player_name}")
                    return False

                conn.commit()
                logging.info(f"✅ Successfully removed stats for {player_name}: -{score} points, -{races_played} races, -{war_participation} war participation")
                return True

        except Exception as e:
            logging.error(f"❌ Error removing player stats with participation for {player_name}: {e}")
            import traceback
            logging.error(f"❌ Full traceback: {traceback.format_exc()}")
            return False

    def get_player_stats(self, player_name: str, guild_id: int = 0) -> Optional[Dict]:
        """Get comprehensive player statistics with cached metrics."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT id, total_score, total_races, war_count, average_score,
                           last_war_date, created_at, updated_at,
                           team, nicknames, added_by, total_team_differential, country_code,
                           -- Cached stable metrics
                           score_stddev, consistency_score, highest_score, lowest_score,
                           wins, losses, ties, win_percentage,
                           -- Cached volatile metrics
                           avg10_score, form_score, clutch_factor, potential, hotstreak,
                           cached_metrics_updated_at
                    FROM players
                    WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (player_name, guild_id))

                result = cursor.fetchone()
                if not result:
                    return None

                average_score = float(result[4]) if result[4] else 0.0
                score_stddev = float(result[13]) if result[13] else 0.0
                total_wars = float(result[3]) if result[3] else 0.0
                cv_percent = (score_stddev / average_score * 100) if average_score > 0 and total_wars >= 2 else None
                consistency_score = max(0, 100 - cv_percent) if cv_percent is not None else None

                return {
                    'player_name': player_name,
                    'total_score': result[1],
                    'total_races': result[2],
                    'war_count': result[3],
                    'average_score': average_score,
                    'last_war_date': result[5].isoformat() if result[5] else None,
                    'stats_created_at': result[6].isoformat() if result[6] else None,
                    'stats_updated_at': result[7].isoformat() if result[7] else None,
                    'team': result[8] if result[8] else 'Unassigned',
                    'nicknames': result[9] if result[9] else [],
                    'added_by': result[10],
                    'total_team_differential': result[11] if result[11] is not None else 0,
                    'country_code': result[12] if result[12] else None,
                    # Cached stable metrics
                    'highest_score': result[15] or 0,
                    'lowest_score': result[16] or 0,
                    'score_stddev': score_stddev,
                    'cv_percent': cv_percent,
                    'consistency_score': float(result[14]) if result[14] is not None else None,
                    'wins': result[17] or 0,
                    'losses': result[18] or 0,
                    'ties': result[19] or 0,
                    'win_percentage': float(result[20]) if result[20] else 0.0,
                    # Cached volatile metrics (may be NULL)
                    'avg10_score': float(result[21]) if result[21] is not None else None,
                    'form_score': float(result[22]) if result[22] is not None else None,
                    'clutch_factor': float(result[23]) if result[23] is not None else None,
                    'potential': float(result[24]) if result[24] is not None else None,
                    'hotstreak': float(result[25]) if result[25] is not None else None,
                }

        except Exception as e:
            logging.error(f"❌ Error getting player stats: {e}")
            return None

    def _refresh_volatile_metrics(self, player_name: str, guild_id: int) -> bool:
        """Recalculate and cache volatile metrics after invalidation."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT id, war_count, average_score
                    FROM players
                    WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (player_name, guild_id))

                result = cursor.fetchone()
                if not result:
                    return False

                player_id, war_count, avg_score = result
                war_count = float(war_count) if war_count else 0.0
                avg_score = float(avg_score) if avg_score else 0.0

                avg10_score = None
                form_score = None
                clutch_factor = None
                potential = None
                hotstreak = None

                if war_count >= 10:
                    avg10_stats = self.get_player_stats_last_x_wars(player_name, 10, guild_id)
                    if avg10_stats:
                        avg10_score = avg10_stats.get('average_score')
                        hotstreak = avg10_score - avg_score if avg10_score else None

                    form_score = self.get_player_form_score(player_name, guild_id)
                    potential = self.get_player_potential(player_name, guild_id)

                if war_count >= 2:
                    clutch_factor = self.get_player_clutch_factor(player_name, guild_id)

                cursor.execute("""
                    UPDATE players
                    SET avg10_score = %s,
                        form_score = %s,
                        clutch_factor = %s,
                        potential = %s,
                        hotstreak = %s,
                        cached_metrics_updated_at = CURRENT_TIMESTAMP
                    WHERE player_name = %s AND guild_id = %s
                """, (avg10_score, form_score, clutch_factor, potential, hotstreak,
                      player_name, guild_id))

                conn.commit()
                logging.info(f"✅ Refreshed cached metrics for {player_name}")
                return True

        except Exception as e:
            logging.error(f"❌ Error refreshing metrics: {e}")
            return False

    def get_player_stats_last_x_wars(self, player_name: str, x_wars: int, guild_id: int = 0) -> Optional[Dict]:
        """Get player statistics calculated from their last X wars only."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT id, team, nicknames, added_by, created_at
                    FROM players
                    WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (player_name, guild_id))

                player_info = cursor.fetchone()
                if not player_info:
                    return None

                player_id = player_info[0]

                cursor.execute("""
                    SELECT
                        w.war_date,
                        w.race_count,
                        w.team_differential,
                        pwp.score,
                        pwp.races_played,
                        pwp.war_participation
                    FROM player_war_performances pwp
                    JOIN wars w ON pwp.war_id = w.id
                    WHERE pwp.player_id = %s AND w.guild_id = %s
                    ORDER BY w.created_at DESC
                    LIMIT %s
                """, (player_id, guild_id, x_wars))

                performances = cursor.fetchall()
                if not performances:
                    return None

                total_score = 0
                total_races = 0
                total_war_participation = 0.0
                total_team_differential = 0
                last_war_date = None
                highest_score = 0
                lowest_score = None
                wins = 0
                losses = 0
                ties = 0
                scores_list = []
                num_wars = len(performances)

                for perf in performances:
                    war_date, race_count, team_diff, score, races_played, war_participation = perf
                    total_score += score
                    total_races += races_played
                    war_participation_float = float(war_participation)
                    total_war_participation += war_participation_float
                    normalized_score = score / war_participation_float if war_participation_float > 0 else score
                    scores_list.append(normalized_score)
                    scaled_differential = int((team_diff or 0) * war_participation_float)
                    total_team_differential += scaled_differential

                    if team_diff is not None:
                        if team_diff > 0:
                            wins += 1
                        elif team_diff < 0:
                            losses += 1
                        else:
                            ties += 1

                    if races_played == 12:
                        if score > highest_score:
                            highest_score = score
                        if lowest_score is None or score < lowest_score:
                            lowest_score = score

                    if war_date and (not last_war_date or war_date > last_war_date):
                        last_war_date = war_date

                average_score = round(total_score / total_war_participation, 2) if total_war_participation > 0 else 0.0

                total_wars = wins + losses + ties
                win_percentage = (wins / total_wars * 100) if total_wars > 0 else 0.0

                if lowest_score is None:
                    lowest_score = 0

                if len(scores_list) > 0:
                    score_stddev = statistics.pstdev(scores_list)
                else:
                    score_stddev = 0.0

                cv_percent = (score_stddev / average_score * 100) if average_score > 0 and len(scores_list) >= 2 else None
                consistency_score = max(0, 100 - cv_percent) if cv_percent is not None else None

                return {
                    'player_name': player_name,
                    'total_score': total_score,
                    'total_races': total_races,
                    'war_count': total_war_participation,
                    'num_wars': num_wars,
                    'average_score': float(average_score),
                    'last_war_date': last_war_date.isoformat() if last_war_date else None,
                    'stats_created_at': player_info[4].isoformat() if player_info[4] else None,
                    'stats_updated_at': None,
                    'team': player_info[1] if player_info[1] else 'Unassigned',
                    'nicknames': player_info[2] if player_info[2] else [],
                    'added_by': player_info[3],
                    'total_team_differential': total_team_differential,
                    'highest_score': highest_score,
                    'lowest_score': lowest_score,
                    'score_stddev': score_stddev,
                    'cv_percent': cv_percent,
                    'consistency_score': consistency_score,
                    'wins': wins,
                    'losses': losses,
                    'ties': ties,
                    'win_percentage': win_percentage
                }

        except Exception as e:
            logging.error(f"❌ Error getting player stats for last {x_wars} wars: {e}")
            return None

    def get_player_form_score(self, player_name: str, guild_id: int = 0) -> Optional[float]:
        """Calculate Form Score (Momentum) using exponentially weighted moving average."""
        try:
            self._validate_guild_id(guild_id, "get_player_form_score")

            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT id FROM players
                    WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (player_name, guild_id))

                player_info = cursor.fetchone()
                if not player_info:
                    return None

                player_id = player_info[0]

                cursor.execute("""
                    SELECT
                        pwp.score,
                        pwp.war_participation
                    FROM player_war_performances pwp
                    JOIN wars w ON pwp.war_id = w.id
                    WHERE pwp.player_id = %s AND w.guild_id = %s
                    ORDER BY w.created_at DESC
                    LIMIT 20
                """, (player_id, guild_id))

                all_performances = cursor.fetchall()

                performances_used = []
                for score, war_participation in all_performances:
                    war_participation_float = float(war_participation)

                    if war_participation_float <= 0:
                        continue

                    normalized_score = score / war_participation_float
                    performances_used.append(normalized_score)

                    if len(performances_used) >= FORM_SCORE_MIN_WARS:
                        break

                if len(performances_used) < FORM_SCORE_MIN_WARS:
                    return None

                weighted_sum = 0.0
                weight_sum = 0.0

                for i, normalized_score in enumerate(performances_used):
                    weight = FORM_SCORE_DECAY_FACTOR ** i
                    weighted_sum += normalized_score * weight
                    weight_sum += weight

                if weight_sum <= 0:
                    logging.warning(f"Unexpected zero weight_sum for {player_name} in guild {guild_id}")
                    return None

                raw_form_score = weighted_sum / weight_sum

                # Convert to soccer-style rating (0.0-10.0+ scale)
                if raw_form_score <= 84:
                    soccer_rating = (raw_form_score / 84.0) * 6.0
                elif raw_form_score <= 100:
                    soccer_rating = 6.0 + ((raw_form_score - 84) / 16.0) * 3.0
                elif raw_form_score <= 110:
                    soccer_rating = 9.0 + ((raw_form_score - 100) / 10.0)
                else:
                    soccer_rating = 10.0 + ((raw_form_score - 110) / 10.0)

                soccer_rating = max(0.0, soccer_rating)
                return round(soccer_rating, 1)

        except Exception as e:
            logging.error(f"❌ Error calculating form score for {player_name}: {e}")
            return None

    @staticmethod
    def get_clutch_category(clutch_factor: Optional[float]) -> Optional[str]:
        """Categorize clutch factor into performance category."""
        if clutch_factor is None:
            return None

        if clutch_factor >= CLUTCH_ELITE_THRESHOLD:
            return "Elite Clutch"
        elif clutch_factor >= CLUTCH_POSITIVE_THRESHOLD:
            return "Clutch"
        elif clutch_factor >= CLUTCH_NEUTRAL_THRESHOLD:
            return "Neutral"
        elif clutch_factor >= CLUTCH_SHAKY_THRESHOLD:
            return "Shaky"
        else:
            return "Chokes"

    def get_player_clutch_factor(self, player_name: str, guild_id: int = 0) -> Optional[float]:
        """Calculate Clutch Factor: performance in close wars vs overall average."""
        try:
            self._validate_guild_id(guild_id, "get_player_clutch_factor")

            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT id FROM players
                    WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (player_name, guild_id))

                player_info = cursor.fetchone()
                if not player_info:
                    return None

                player_id = player_info[0]

                cursor.execute("""
                    SELECT pwp.score, w.team_differential, pwp.war_participation
                    FROM player_war_performances pwp
                    JOIN wars w ON pwp.war_id = w.id
                    WHERE pwp.player_id = %s AND w.guild_id = %s
                    ORDER BY w.created_at DESC
                """, (player_id, guild_id))

                performances = cursor.fetchall()

                if len(performances) < 2:
                    return None

                all_scores = []
                close_war_scores = []

                for score, team_diff, war_participation in performances:
                    war_participation_float = float(war_participation)

                    if war_participation_float <= 0:
                        continue

                    normalized_score = score / war_participation_float
                    all_scores.append(normalized_score)

                    if team_diff is not None and abs(team_diff) <= CLOSE_WAR_THRESHOLD:
                        close_war_scores.append(normalized_score)

                if len(all_scores) < 2 or len(close_war_scores) < 1:
                    return None

                avg_all = statistics.mean(all_scores)
                stddev = statistics.pstdev(all_scores)
                avg_close = statistics.mean(close_war_scores)

                if stddev <= 0:
                    return None

                clutch_factor = (avg_close - avg_all) / stddev
                return round(clutch_factor, 2)

        except Exception as e:
            logging.error(f"❌ Error calculating clutch factor for {player_name}: {e}")
            return None

    def get_player_potential(self, player_name: str, guild_id: int = 0) -> Optional[float]:
        """Calculate Potential: estimated performance ceiling based on recent form + variance."""
        try:
            self._validate_guild_id(guild_id, "get_player_potential")

            avg10_stats = self.get_player_stats_last_x_wars(player_name, 10, guild_id)
            if not avg10_stats:
                return None

            num_wars = avg10_stats.get('num_wars', 0)
            if num_wars < 10:
                return None

            avg10_score = avg10_stats.get('average_score')
            if avg10_score is None or avg10_score <= 0:
                return None

            overall_stats = self.get_player_stats(player_name, guild_id)
            if not overall_stats:
                return None

            stddev = overall_stats.get('score_stddev', 0.0)
            potential = avg10_score + stddev
            return round(potential, 1)

        except Exception as e:
            logging.error(f"❌ Error calculating potential for {player_name}: {e}")
            return None

    def get_player_distinct_war_count(self, player_name: str, guild_id: int = 0) -> int:
        """Get the number of distinct wars a player has participated in."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT COUNT(*)
                    FROM player_war_performances pwp
                    JOIN players p ON pwp.player_id = p.id
                    WHERE p.player_name = %s AND p.guild_id = %s
                """, (player_name, guild_id))

                count = cursor.fetchone()[0]
                logging.info(f"✅ Player {player_name} participated in {count} distinct wars")
                return count

        except Exception as e:
            logging.error(f"❌ Error getting distinct war count for {player_name}: {e}")
            return 0

    def get_player_last_war_scores(self, player_name: str, limit: int = 10, guild_id: int = 0) -> List[Dict]:
        """Get the last N war scores for a player."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT id
                    FROM players
                    WHERE player_name = %s AND guild_id = %s AND is_active = TRUE
                """, (player_name, guild_id))

                result = cursor.fetchone()
                if not result:
                    return []

                player_id = result[0]

                cursor.execute("""
                    SELECT w.war_date, pwp.score, w.race_count
                    FROM player_war_performances pwp
                    JOIN wars w ON pwp.war_id = w.id
                    WHERE pwp.player_id = %s AND w.guild_id = %s
                    ORDER BY w.created_at DESC
                    LIMIT %s
                """, (player_id, guild_id, limit))

                results = cursor.fetchall()
                return [
                    {
                        'war_date': row[0].isoformat() if row[0] else None,
                        'score': row[1],
                        'race_count': row[2]
                    }
                    for row in results
                ]

        except Exception as e:
            logging.error(f"❌ Error getting last war scores for {player_name}: {e}")
            return []
