"""
Stats repository: Player statistics, metrics calculation, and caching.
"""

import logging
import statistics
import traceback

from ..constants import (
    CLOSE_WAR_THRESHOLD,
    CLUTCH_ELITE_THRESHOLD,
    CLUTCH_NEUTRAL_THRESHOLD,
    CLUTCH_POSITIVE_THRESHOLD,
    CLUTCH_SHAKY_THRESHOLD,
    FORM_SCORE_DECAY_FACTOR,
    FORM_SCORE_MIN_WARS,
)
from .base import BaseRepository


def _float_or_none(val) -> float | None:
    """Convert to float if not None, else return None."""
    return float(val) if val is not None else None


def _float_or_zero(val) -> float:
    """Convert to float if truthy, else return 0.0."""
    return float(val) if val else 0.0


def _iso_or_none(val) -> str | None:
    """Convert to ISO string if not None, else return None."""
    return val.isoformat() if val else None


def _int_or_zero(val) -> int:
    """Return val if not None, else 0."""
    return val if val is not None else 0


def _build_player_stats_dict(player_name: str, result) -> dict:
    """Build player stats dict from a database row."""
    avg = _float_or_zero(result[4])
    stddev = _float_or_zero(result[13])
    wars = _float_or_zero(result[3])
    cv = (stddev / avg * 100) if avg > 0 and wars >= 2 else None

    return {
        'player_name': player_name,
        'total_score': result[1],
        'total_races': result[2],
        'war_count': result[3],
        'average_score': avg,
        'last_war_date': _iso_or_none(result[5]),
        'stats_created_at': _iso_or_none(result[6]),
        'stats_updated_at': _iso_or_none(result[7]),
        'team': result[8] or 'Unassigned',
        'nicknames': result[9] or [],
        'added_by': result[10],
        'total_team_differential': _int_or_zero(result[11]),
        'country_code': result[12] or None,
        'highest_score': result[15] or 0,
        'lowest_score': result[16] or 0,
        'score_stddev': stddev,
        'cv_percent': cv,
        'consistency_score': _float_or_none(result[14]),
        'wins': result[17] or 0,
        'losses': result[18] or 0,
        'ties': result[19] or 0,
        'win_percentage': _float_or_zero(result[20]),
        'avg10_score': _float_or_none(result[21]),
        'form_score': _float_or_none(result[22]),
        'clutch_factor': _float_or_none(result[23]),
        'potential': _float_or_none(result[24]),
        'hotstreak': _float_or_none(result[25]),
    }


def _classify_war_result(team_diff) -> tuple[int, int, int]:
    """Classify a team differential into (wins, losses, ties) increments."""
    if team_diff is None:
        return (0, 0, 0)
    if team_diff > 0:
        return (1, 0, 0)
    if team_diff < 0:
        return (0, 1, 0)
    return (0, 0, 1)


def _update_score_extremes(
    score: int, races_played: int, highest: int, lowest: int | None
) -> tuple[int, int | None]:
    """Update highest/lowest scores for full 12-race wars."""
    if races_played != 12:
        return highest, lowest
    highest = max(highest, score)
    lowest = score if lowest is None else min(lowest, score)
    return highest, lowest


def _accumulate_war_stats(performances: list) -> dict:
    """Accumulate statistics from a list of war performance records.

    Returns a dict with totals, win/loss/tie counts, score tracking, etc.
    """
    total_score = 0
    total_races = 0
    total_war_participation = 0.0
    total_team_differential = 0
    last_war_date = None
    highest_score = 0
    lowest_score: int | None = None
    wins = 0
    losses = 0
    ties = 0
    scores_list: list[float] = []

    for perf in performances:
        war_date, _, team_diff, score, races_played_val, war_participation = (
            perf[0], perf[1], perf[2], perf[3], perf[4], perf[5]
        )
        total_score += score
        total_races += races_played_val
        wp = float(war_participation)
        total_war_participation += wp
        normalized_score = score / wp if wp > 0 else score
        scores_list.append(normalized_score)
        total_team_differential += int((team_diff or 0) * wp)

        w, l, t = _classify_war_result(team_diff)
        wins += w
        losses += l
        ties += t

        highest_score, lowest_score = _update_score_extremes(
            score, races_played_val, highest_score, lowest_score
        )

        if war_date and (not last_war_date or war_date > last_war_date):
            last_war_date = war_date

    return {
        'total_score': total_score,
        'total_races': total_races,
        'total_war_participation': total_war_participation,
        'total_team_differential': total_team_differential,
        'last_war_date': last_war_date,
        'highest_score': highest_score,
        'lowest_score': lowest_score if lowest_score is not None else 0,
        'wins': wins,
        'losses': losses,
        'ties': ties,
        'scores_list': scores_list,
    }


class StatsRepository(BaseRepository):
    """Handles all player statistics and metrics operations."""

    async def update_player_stats(self, player_name: str, score: int, races_played: int, war_participation: float, war_date: str, guild_id: int = 0, team_differential: int = 0) -> bool:
        """Update player statistics when a war is added with fractional war support.

        Also updates stable metrics and invalidates volatile metrics for cache.
        """
        self._validate_guild_id(guild_id, "update_player_stats")
        try:
            async with self.get_connection() as conn:
                result = await conn.fetchrow("""
                    SELECT id, total_score, total_races, war_count, total_team_differential
                    FROM players WHERE player_name = $1 AND guild_id = $2 AND is_active = TRUE
                """, player_name, guild_id)

                if result:
                    player_id = result[0]
                    new_total_score = result[1] + score
                    new_total_races = result[2] + races_played
                    new_war_count = float(result[3]) + war_participation
                    scaled_differential = int(team_differential * war_participation)
                    new_total_differential = (result[4] or 0) + scaled_differential
                    new_average = round(new_total_score / new_war_count, 2)

                    # Parameters mapped to $1-$25:
                    # $1=new_total_score, $2=new_total_races, $3=new_war_count,
                    # $4=new_average, $5=war_date, $6=new_total_differential,
                    # $7=player_id (stddev), $8=player_id (max), $9=player_id (min),
                    # $10=player_id (wins), $11=guild_id (wins),
                    # $12=player_id (losses), $13=guild_id (losses),
                    # $14=player_id (ties), $15=guild_id (ties),
                    # $16=new_war_count (consistency WHEN), $17=new_average (consistency WHEN),
                    # $18=player_id (consistency stddev), $19=new_average (consistency divisor),
                    # $20=new_war_count (win_pct WHEN), $21=player_id (win_pct subquery),
                    # $22=guild_id (win_pct subquery), $23=new_war_count (win_pct divisor),
                    # $24=player_name (WHERE), $25=guild_id (WHERE)
                    await conn.execute("""
                        UPDATE players
                        SET total_score = $1, total_races = $2, war_count = $3,
                            average_score = $4, last_war_date = $5, total_team_differential = $6,
                            -- Recalculate stable metrics via subqueries
                            score_stddev = COALESCE((
                                SELECT STDDEV_POP(score) FROM player_war_performances
                                WHERE player_id = $7
                            ), 0.0),
                            highest_score = COALESCE((
                                SELECT MAX(score) FROM player_war_performances
                                WHERE player_id = $8 AND races_played = 12
                            ), 0),
                            lowest_score = COALESCE((
                                SELECT MIN(score) FROM player_war_performances
                                WHERE player_id = $9 AND races_played = 12
                            ), 0),
                            wins = COALESCE((
                                SELECT COUNT(*) FROM player_war_performances pwp
                                JOIN wars w ON pwp.war_id = w.id
                                WHERE pwp.player_id = $10 AND w.team_differential > 0 AND w.guild_id = $11
                            ), 0),
                            losses = COALESCE((
                                SELECT COUNT(*) FROM player_war_performances pwp
                                JOIN wars w ON pwp.war_id = w.id
                                WHERE pwp.player_id = $12 AND w.team_differential < 0 AND w.guild_id = $13
                            ), 0),
                            ties = COALESCE((
                                SELECT COUNT(*) FROM player_war_performances pwp
                                JOIN wars w ON pwp.war_id = w.id
                                WHERE pwp.player_id = $14 AND w.team_differential = 0 AND w.guild_id = $15
                            ), 0),
                            consistency_score = CASE
                                WHEN $16 >= 2 AND $17 > 0
                                THEN GREATEST(0, 100 - (
                                    COALESCE((
                                        SELECT STDDEV_POP(score) FROM player_war_performances
                                        WHERE player_id = $18
                                    ), 0.0) / $19 * 100
                                ))
                                ELSE NULL
                            END,
                            win_percentage = CASE
                                WHEN $20 > 0
                                THEN (COALESCE((
                                    SELECT COUNT(*) FROM player_war_performances pwp
                                    JOIN wars w ON pwp.war_id = w.id
                                    WHERE pwp.player_id = $21 AND w.team_differential > 0 AND w.guild_id = $22
                                ), 0)::DECIMAL / $23 * 100)
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
                        WHERE player_name = $24 AND guild_id = $25
                    """, new_total_score, new_total_races, new_war_count, new_average, war_date, new_total_differential,
                         player_id, player_id, player_id, player_id, guild_id, player_id, guild_id, player_id, guild_id,
                         new_war_count, new_average, player_id, new_average,
                         new_war_count, player_id, guild_id, new_war_count,
                         player_name, guild_id)
                else:
                    logging.error(f"Player {player_name} not found in players table for guild {guild_id}")
                    return False

                logging.info(f"Updated stats for {player_name}: +{score} points, +{races_played} races, +{war_participation} wars, differential: {team_differential:+d}")
                return True

        except Exception as e:
            logging.error(f"Error updating player stats: {e}")
            return False

    async def remove_player_stats_with_participation(self, player_name: str, score: int, races_played: int, war_participation: float, guild_id: int = 0, team_differential: int = 0) -> bool:
        """Remove player statistics when a war is removed, accounting for war participation."""
        self._validate_guild_id(guild_id, "remove_player_stats_with_participation")
        logging.info(f"Attempting to remove stats for player: {player_name}, guild_id: {guild_id}")
        logging.info(f"    Score to remove: {score}, Races: {races_played}, War participation: {war_participation}, Differential: {team_differential}")

        try:
            async with self.get_connection() as conn:
                logging.info(f"Querying for player: {player_name} in guild {guild_id}")
                result = await conn.fetchrow("""
                    SELECT total_score, total_races, war_count, total_team_differential
                    FROM players WHERE player_name = $1 AND guild_id = $2 AND is_active = TRUE
                """, player_name, guild_id)

                if not result:
                    logging.warning(f"No stats found for {player_name} in guild {guild_id} (or player inactive)")

                    all_matches = await conn.fetch(
                        "SELECT player_name, guild_id, is_active FROM players WHERE player_name = $1", player_name
                    )
                    if all_matches:
                        logging.warning(f"Player '{player_name}' exists but in different states: {[(r[0], r[1], r[2]) for r in all_matches]}")
                    else:
                        logging.warning(f"Player '{player_name}' does not exist in players table at all")
                    return False

                current_total_score, current_total_races, current_war_count, current_total_differential = result[0], result[1], result[2], result[3]
                logging.info(f"Found player {player_name}: current stats = {current_total_score} points, {current_total_races} races, {current_war_count} wars, differential: {current_total_differential}")

                current_war_count = float(current_war_count)

                new_total_score = max(0, current_total_score - score)
                new_total_races = max(0, current_total_races - races_played)
                new_war_count = max(0.0, current_war_count - war_participation)
                scaled_differential = int(team_differential * war_participation)
                new_total_differential = (current_total_differential or 0) - scaled_differential

                logging.info(f"Calculated new stats: {new_total_score} points, {new_total_races} races, {new_war_count} wars, differential: {new_total_differential}")

                if new_war_count > 0:
                    new_average = round(new_total_score / new_war_count, 2)
                else:
                    new_average = 0.0

                logging.info(f"New average score: {new_average}")

                player_row = await conn.fetchrow("""
                    SELECT id FROM players
                    WHERE player_name = $1 AND guild_id = $2
                """, player_name, guild_id)

                if not player_row:
                    logging.error(f"Could not get player ID for {player_name}")
                    return False

                player_id = player_row[0]

                logging.info(f"Executing UPDATE for player {player_name}")
                # Parameters mapped to $1-$24:
                # $1=new_total_score, $2=new_total_races, $3=new_war_count,
                # $4=new_average, $5=new_total_differential,
                # $6=player_id (stddev), $7=player_id (max), $8=player_id (min),
                # $9=player_id (wins), $10=guild_id (wins),
                # $11=player_id (losses), $12=guild_id (losses),
                # $13=player_id (ties), $14=guild_id (ties),
                # $15=new_war_count (consistency WHEN), $16=new_average (consistency WHEN),
                # $17=player_id (consistency stddev), $18=new_average (consistency divisor),
                # $19=new_war_count (win_pct WHEN), $20=player_id (win_pct subquery),
                # $21=guild_id (win_pct subquery), $22=new_war_count (win_pct divisor),
                # $23=player_name (WHERE), $24=guild_id (WHERE)
                status = await conn.execute("""
                    UPDATE players
                    SET total_score = $1, total_races = $2, war_count = $3,
                        average_score = $4, total_team_differential = $5,
                        -- Recalculate stable metrics via subqueries
                        score_stddev = COALESCE((
                            SELECT STDDEV_POP(score) FROM player_war_performances
                            WHERE player_id = $6
                        ), 0.0),
                        highest_score = COALESCE((
                            SELECT MAX(score) FROM player_war_performances
                            WHERE player_id = $7 AND races_played = 12
                        ), 0),
                        lowest_score = COALESCE((
                            SELECT MIN(score) FROM player_war_performances
                            WHERE player_id = $8 AND races_played = 12
                        ), 0),
                        wins = COALESCE((
                            SELECT COUNT(*) FROM player_war_performances pwp
                            JOIN wars w ON pwp.war_id = w.id
                            WHERE pwp.player_id = $9 AND w.team_differential > 0 AND w.guild_id = $10
                        ), 0),
                        losses = COALESCE((
                            SELECT COUNT(*) FROM player_war_performances pwp
                            JOIN wars w ON pwp.war_id = w.id
                            WHERE pwp.player_id = $11 AND w.team_differential < 0 AND w.guild_id = $12
                        ), 0),
                        ties = COALESCE((
                            SELECT COUNT(*) FROM player_war_performances pwp
                            JOIN wars w ON pwp.war_id = w.id
                            WHERE pwp.player_id = $13 AND w.team_differential = 0 AND w.guild_id = $14
                        ), 0),
                        consistency_score = CASE
                            WHEN $15 >= 2 AND $16 > 0
                            THEN GREATEST(0, 100 - (
                                COALESCE((
                                    SELECT STDDEV_POP(score) FROM player_war_performances
                                    WHERE player_id = $17
                                ), 0.0) / $18 * 100
                            ))
                            ELSE NULL
                        END,
                        win_percentage = CASE
                            WHEN $19 > 0
                            THEN (COALESCE((
                                SELECT COUNT(*) FROM player_war_performances pwp
                                JOIN wars w ON pwp.war_id = w.id
                                WHERE pwp.player_id = $20 AND w.team_differential > 0 AND w.guild_id = $21
                            ), 0)::DECIMAL / $22 * 100)
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
                    WHERE player_name = $23 AND guild_id = $24
                """, new_total_score, new_total_races, new_war_count, new_average, new_total_differential,
                     player_id, player_id, player_id, player_id, guild_id, player_id, guild_id, player_id, guild_id,
                     new_war_count, new_average, player_id, new_average,
                     new_war_count, player_id, guild_id, new_war_count,
                     player_name, guild_id)

                rows_affected = int(status.split()[-1])
                logging.info(f"UPDATE affected {rows_affected} rows")

                if rows_affected == 0:
                    logging.warning(f"UPDATE statement affected 0 rows for player {player_name}")
                    return False

                logging.info(f"Successfully removed stats for {player_name}: -{score} points, -{races_played} races, -{war_participation} war participation")
                return True

        except Exception as e:
            logging.error(f"Error removing player stats with participation for {player_name}: {e}")
            logging.error(f"Full traceback: {traceback.format_exc()}")
            return False

    async def get_player_stats(self, player_name: str, guild_id: int = 0) -> dict | None:
        """Get comprehensive player statistics with cached metrics."""
        self._validate_guild_id(guild_id, "get_player_stats")
        try:
            async with self.get_connection() as conn:
                result = await conn.fetchrow("""
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
                    WHERE player_name = $1 AND guild_id = $2 AND is_active = TRUE
                """, player_name, guild_id)

                if not result:
                    return None

                return _build_player_stats_dict(player_name, result)

        except Exception as e:
            logging.error(f"Error getting player stats: {e}")
            return None

    async def _refresh_volatile_metrics(self, player_name: str, guild_id: int) -> bool:
        """Recalculate and cache volatile metrics after invalidation."""
        self._validate_guild_id(guild_id, "_refresh_volatile_metrics")
        try:
            async with self.get_connection() as conn:
                result = await conn.fetchrow("""
                    SELECT id, war_count, average_score
                    FROM players
                    WHERE player_name = $1 AND guild_id = $2 AND is_active = TRUE
                """, player_name, guild_id)

                if not result:
                    return False

                _, war_count, avg_score = result[0], result[1], result[2]
                war_count = float(war_count) if war_count else 0.0
                avg_score = float(avg_score) if avg_score else 0.0

                avg10_score = None
                form_score = None
                clutch_factor = None
                potential = None
                hotstreak = None

                if war_count >= 10:
                    avg10_stats = await self.get_player_stats_last_x_wars(player_name, 10, guild_id)
                    if avg10_stats:
                        avg10_score = avg10_stats.get('average_score')
                        hotstreak = avg10_score - avg_score if avg10_score else None

                    form_score = await self.get_player_form_score(player_name, guild_id)
                    potential = await self.get_player_potential(player_name, guild_id)

                if war_count >= 2:
                    clutch_factor = await self.get_player_clutch_factor(player_name, guild_id)

                await conn.execute("""
                    UPDATE players
                    SET avg10_score = $1,
                        form_score = $2,
                        clutch_factor = $3,
                        potential = $4,
                        hotstreak = $5,
                        cached_metrics_updated_at = CURRENT_TIMESTAMP
                    WHERE player_name = $6 AND guild_id = $7
                """, avg10_score, form_score, clutch_factor, potential, hotstreak,
                     player_name, guild_id)

                logging.info(f"Refreshed cached metrics for {player_name}")
                return True

        except Exception as e:
            logging.error(f"Error refreshing metrics: {e}")
            return False

    async def get_player_stats_last_x_wars(self, player_name: str, x_wars: int, guild_id: int = 0) -> dict | None:
        """Get player statistics calculated from their last X wars only."""
        self._validate_guild_id(guild_id, "get_player_stats_last_x_wars")
        try:
            async with self.get_connection() as conn:
                player_info = await conn.fetchrow("""
                    SELECT id, team, nicknames, added_by, created_at
                    FROM players
                    WHERE player_name = $1 AND guild_id = $2 AND is_active = TRUE
                """, player_name, guild_id)

                if not player_info:
                    return None

                player_id = player_info[0]

                performances = await conn.fetch("""
                    SELECT
                        w.war_date,
                        w.race_count,
                        w.team_differential,
                        pwp.score,
                        pwp.races_played,
                        pwp.war_participation
                    FROM player_war_performances pwp
                    JOIN wars w ON pwp.war_id = w.id
                    WHERE pwp.player_id = $1 AND w.guild_id = $2
                    ORDER BY w.created_at DESC
                    LIMIT $3
                """, player_id, guild_id, x_wars)

                if not performances:
                    return None

                acc = _accumulate_war_stats(performances)
                twp = acc['total_war_participation']
                average_score = round(acc['total_score'] / twp, 2) if twp > 0 else 0.0

                total_wars = acc['wins'] + acc['losses'] + acc['ties']
                win_percentage = (acc['wins'] / total_wars * 100) if total_wars > 0 else 0.0

                scores_list = acc['scores_list']
                score_stddev = statistics.pstdev(scores_list) if scores_list else 0.0
                cv_percent = (score_stddev / average_score * 100) if average_score > 0 and len(scores_list) >= 2 else None
                consistency_score = max(0, 100 - cv_percent) if cv_percent is not None else None

                return {
                    'player_name': player_name,
                    'total_score': acc['total_score'],
                    'total_races': acc['total_races'],
                    'war_count': twp,
                    'num_wars': len(performances),
                    'average_score': float(average_score),
                    'last_war_date': acc['last_war_date'].isoformat() if acc['last_war_date'] else None,
                    'stats_created_at': player_info[4].isoformat() if player_info[4] else None,
                    'stats_updated_at': None,
                    'team': player_info[1] if player_info[1] else 'Unassigned',
                    'nicknames': player_info[2] if player_info[2] else [],
                    'added_by': player_info[3],
                    'total_team_differential': acc['total_team_differential'],
                    'highest_score': acc['highest_score'],
                    'lowest_score': acc['lowest_score'],
                    'score_stddev': score_stddev,
                    'cv_percent': cv_percent,
                    'consistency_score': consistency_score,
                    'wins': acc['wins'],
                    'losses': acc['losses'],
                    'ties': acc['ties'],
                    'win_percentage': win_percentage,
                }

        except Exception as e:
            logging.error(f"Error getting player stats for last {x_wars} wars: {e}")
            return None

    async def get_player_form_score(self, player_name: str, guild_id: int = 0) -> float | None:
        """Calculate Form Score (Momentum) using exponentially weighted moving average."""
        try:
            self._validate_guild_id(guild_id, "get_player_form_score")

            async with self.get_connection() as conn:
                player_info = await conn.fetchrow("""
                    SELECT id FROM players
                    WHERE player_name = $1 AND guild_id = $2 AND is_active = TRUE
                """, player_name, guild_id)

                if not player_info:
                    return None

                player_id = player_info[0]

                all_performances = await conn.fetch("""
                    SELECT
                        pwp.score,
                        pwp.war_participation
                    FROM player_war_performances pwp
                    JOIN wars w ON pwp.war_id = w.id
                    WHERE pwp.player_id = $1 AND w.guild_id = $2
                    ORDER BY w.created_at DESC
                    LIMIT 20
                """, player_id, guild_id)

                performances_used = []
                for row in all_performances:
                    score_val = row[0]
                    war_participation = row[1]
                    war_participation_float = float(war_participation)

                    if war_participation_float <= 0:
                        continue

                    normalized_score = score_val / war_participation_float
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
            logging.error(f"Error calculating form score for {player_name}: {e}")
            return None

    @staticmethod
    def get_clutch_category(clutch_factor: float | None) -> str | None:
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

    async def get_player_clutch_factor(self, player_name: str, guild_id: int = 0) -> float | None:
        """Calculate Clutch Factor: performance in close wars vs overall average."""
        try:
            self._validate_guild_id(guild_id, "get_player_clutch_factor")

            async with self.get_connection() as conn:
                player_info = await conn.fetchrow("""
                    SELECT id FROM players
                    WHERE player_name = $1 AND guild_id = $2 AND is_active = TRUE
                """, player_name, guild_id)

                if not player_info:
                    return None

                player_id = player_info[0]

                performances = await conn.fetch("""
                    SELECT pwp.score, w.team_differential, pwp.war_participation
                    FROM player_war_performances pwp
                    JOIN wars w ON pwp.war_id = w.id
                    WHERE pwp.player_id = $1 AND w.guild_id = $2
                    ORDER BY w.created_at DESC
                """, player_id, guild_id)

                if len(performances) < 2:
                    return None

                all_scores = []
                close_war_scores = []

                for row in performances:
                    score_val = row[0]
                    team_diff = row[1]
                    war_participation = row[2]
                    war_participation_float = float(war_participation)

                    if war_participation_float <= 0:
                        continue

                    normalized_score = score_val / war_participation_float
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
            logging.error(f"Error calculating clutch factor for {player_name}: {e}")
            return None

    async def get_player_potential(self, player_name: str, guild_id: int = 0) -> float | None:
        """Calculate Potential: estimated performance ceiling based on recent form + variance."""
        try:
            self._validate_guild_id(guild_id, "get_player_potential")

            avg10_stats = await self.get_player_stats_last_x_wars(player_name, 10, guild_id)
            if not avg10_stats:
                return None

            num_wars = avg10_stats.get('num_wars', 0)
            if num_wars < 10:
                return None

            avg10_score = avg10_stats.get('average_score')
            if avg10_score is None or avg10_score <= 0:
                return None

            overall_stats = await self.get_player_stats(player_name, guild_id)
            if not overall_stats:
                return None

            stddev = overall_stats.get('score_stddev', 0.0)
            potential = avg10_score + stddev
            return round(potential, 1)

        except Exception as e:
            logging.error(f"Error calculating potential for {player_name}: {e}")
            return None

    async def get_player_distinct_war_count(self, player_name: str, guild_id: int = 0) -> int:
        """Get the number of distinct wars a player has participated in."""
        self._validate_guild_id(guild_id, "get_player_distinct_war_count")
        try:
            async with self.get_connection() as conn:
                count = await conn.fetchval("""
                    SELECT COUNT(*)
                    FROM player_war_performances pwp
                    JOIN players p ON pwp.player_id = p.id
                    WHERE p.player_name = $1 AND p.guild_id = $2
                """, player_name, guild_id)

                logging.info(f"Player {player_name} participated in {count} distinct wars")
                return count

        except Exception as e:
            logging.error(f"Error getting distinct war count for {player_name}: {e}")
            return 0

    async def get_player_last_war_scores(self, player_name: str, limit: int = 10, guild_id: int = 0) -> list[dict]:
        """Get the last N war scores for a player."""
        self._validate_guild_id(guild_id, "get_player_last_war_scores")
        try:
            async with self.get_connection() as conn:
                result = await conn.fetchrow("""
                    SELECT id
                    FROM players
                    WHERE player_name = $1 AND guild_id = $2 AND is_active = TRUE
                """, player_name, guild_id)

                if not result:
                    return []

                player_id = result[0]

                rows = await conn.fetch("""
                    SELECT w.war_date, pwp.score, w.race_count
                    FROM player_war_performances pwp
                    JOIN wars w ON pwp.war_id = w.id
                    WHERE pwp.player_id = $1 AND w.guild_id = $2
                    ORDER BY w.created_at DESC
                    LIMIT $3
                """, player_id, guild_id, limit)

                return [
                    {
                        'war_date': row[0].isoformat() if row[0] else None,
                        'score': row[1],
                        'race_count': row[2]
                    }
                    for row in rows
                ]

        except Exception as e:
            logging.error(f"Error getting last war scores for {player_name}: {e}")
            return []
