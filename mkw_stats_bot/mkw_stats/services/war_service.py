"""
War service: Single entry point for war submission, removal, and modification.

Replaces duplicated war submission logic that was in:
- commands.py (addwar_slash)
- bot.py (handle_ocr_war_submission_from_view)
- bot.py (handle_ocr_war_submission)
- bot.py (handle_bulk_results_save)
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Optional

from ..constants import TOTAL_POINTS_PER_RACE

logger = logging.getLogger(__name__)


@dataclass
class WarSubmissionResult:
    """Result of a war submission attempt."""
    success: bool
    war_id: Optional[int] = None
    stats_updated: Optional[List[str]] = None
    stats_failed: Optional[List[str]] = None
    team_score: int = 0
    team_differential: int = 0
    error: Optional[str] = None


class WarService:
    """Centralizes all war submission logic.

    This is the single entry point for adding, removing, and modifying wars.
    All callers (slash commands, OCR, bulk scan) use this instead of
    calling db.add_race_results + db.update_player_stats directly.
    """

    def __init__(self, db):
        """
        Args:
            db: DatabaseManager instance
        """
        self.db = db

    def submit_war(
        self,
        results: List[Dict],
        race_count: int,
        guild_id: int,
    ) -> WarSubmissionResult:
        """Submit a war and update all player statistics.

        This is the single entry point replacing duplicated logic in 4 places.

        Args:
            results: List of player results. Each dict must have:
                - 'name': str (resolved player name)
                - 'score': int
                - 'races' or 'races_played': int (individual race count)
                Optional:
                - 'war_participation': float (auto-calculated if missing)
            race_count: Total races in this war (max of individual race counts)
            guild_id: Guild ID for data isolation

        Returns:
            WarSubmissionResult with war_id, stats tracking, and error info
        """
        try:
            # Normalize results to ensure consistent field names
            normalized = self._normalize_results(results, race_count)

            # Step 1: Add war to database
            war_id = self.db.wars.add_race_results(normalized, race_count, guild_id=guild_id)

            if war_id is None:
                return WarSubmissionResult(
                    success=False,
                    error="Failed to add war to database"
                )

            # Step 2: Calculate team differential
            team_score = sum(r['score'] for r in normalized)
            total_points = TOTAL_POINTS_PER_RACE * race_count
            opponent_score = total_points - team_score
            team_differential = team_score - opponent_score

            # Step 3: Update player statistics
            current_date = self._get_eastern_date()
            stats_updated = []
            stats_failed = []

            for result in normalized:
                races_played = result.get('races_played', result.get('races', race_count))
                war_participation = result.get('war_participation', races_played / race_count if race_count > 0 else 1.0)

                success = self.db.stats.update_player_stats(
                    result['name'],
                    result['score'],
                    races_played,
                    war_participation,
                    current_date,
                    guild_id,
                    team_differential
                )

                if success:
                    stats_updated.append(result['name'])
                else:
                    stats_failed.append(result['name'])

            logger.info(
                f"✅ War {war_id} submitted: {len(stats_updated)} stats updated, "
                f"{len(stats_failed)} failed, differential: {team_differential:+d}"
            )

            return WarSubmissionResult(
                success=True,
                war_id=war_id,
                stats_updated=stats_updated,
                stats_failed=stats_failed,
                team_score=team_score,
                team_differential=team_differential,
            )

        except Exception as e:
            logger.error(f"❌ War submission failed: {e}")
            return WarSubmissionResult(
                success=False,
                error=str(e)
            )

    def submit_appended_players(
        self,
        war_id: int,
        new_players: List[Dict],
        guild_id: int,
    ) -> WarSubmissionResult:
        """Update stats for players appended to an existing war.

        Called after db.wars.append_players_to_war_by_id() succeeds.
        Calculates the updated team differential and updates stats for new players only.

        Args:
            war_id: The war ID that was updated
            new_players: List of newly added player dicts (name, score, races_played, war_participation)
            guild_id: Guild ID
        """
        try:
            # Get the updated war to compute new team differential
            updated_war = self.db.wars.get_war_by_id(war_id, guild_id)
            if not updated_war:
                return WarSubmissionResult(success=False, error=f"War {war_id} not found")

            all_results = updated_war.get('results', [])
            race_count = updated_war.get('race_count', 12)
            team_score = sum(p['score'] for p in all_results)
            total_points = TOTAL_POINTS_PER_RACE * race_count
            opponent_score = total_points - team_score
            team_differential = team_score - opponent_score

            current_date = self._get_eastern_date()
            stats_updated = []
            stats_failed = []

            for player in new_players:
                races_played = player.get('races_played', race_count)
                war_participation = player.get('war_participation', races_played / race_count if race_count > 0 else 1.0)

                success = self.db.stats.update_player_stats(
                    player['name'],
                    player['score'],
                    races_played,
                    war_participation,
                    current_date,
                    guild_id,
                    team_differential
                )

                if success:
                    stats_updated.append(player['name'])
                else:
                    stats_failed.append(player['name'])

            return WarSubmissionResult(
                success=True,
                war_id=war_id,
                stats_updated=stats_updated,
                stats_failed=stats_failed,
                team_score=team_score,
                team_differential=team_differential,
            )

        except Exception as e:
            logger.error(f"❌ Failed to update stats for appended players: {e}")
            return WarSubmissionResult(success=False, error=str(e))

    def check_duplicate(self, results: List[Dict], guild_id: int) -> bool:
        """Check if the war results are a duplicate of the last war.

        Args:
            results: Player results to check
            guild_id: Guild ID

        Returns:
            True if this appears to be a duplicate war
        """
        last_war = self.db.wars.get_last_war_for_duplicate_check(guild_id)
        return self.db.wars.check_for_duplicate_war(results, last_war)

    @staticmethod
    def calculate_team_differential(results: List[Dict], race_count: int) -> int:
        """Calculate team differential from results.

        Args:
            results: Player results with 'score' key
            race_count: Total races in the war

        Returns:
            Team differential (positive = win, negative = loss)
        """
        team_score = sum(r.get('score', 0) for r in results)
        total_points = TOTAL_POINTS_PER_RACE * race_count
        opponent_score = total_points - team_score
        return team_score - opponent_score

    def _normalize_results(self, results: List[Dict], race_count: int) -> List[Dict]:
        """Normalize result dicts to have consistent field names.

        Handles both OCR format ('races') and manual format ('races_played').
        """
        normalized = []
        for r in results:
            races_played = r.get('races_played', r.get('races', race_count))
            war_participation = r.get('war_participation', races_played / race_count if race_count > 0 else 1.0)

            entry = {
                'name': r['name'],
                'score': r['score'],
                'races_played': races_played,
                'races': races_played,  # Keep both for backward compat
                'war_participation': war_participation,
            }

            # Preserve extra fields that callers may have added
            for key in ('raw_line', 'raw_name', 'original_name', 'raw_input'):
                if key in r:
                    entry[key] = r[key]

            normalized.append(entry)

        return normalized

    @staticmethod
    def _get_eastern_date() -> str:
        """Get current date in Eastern Time as ISO string."""
        try:
            import zoneinfo
            eastern_tz = zoneinfo.ZoneInfo('America/New_York')
            return datetime.now(eastern_tz).strftime('%Y-%m-%d')
        except (ImportError, KeyError):
            import pytz
            return datetime.now(pytz.timezone('America/New_York')).strftime('%Y-%m-%d')
