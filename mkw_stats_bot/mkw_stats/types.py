"""
Shared type definitions for the MKW Stats Bot.

TypedDicts and dataclasses that flow between modules.
Keeps type information centralized to avoid circular imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypedDict

# =============================================================================
# OCR Result Types
# =============================================================================

class PlayerResult(TypedDict):
    """A single player's result from a war (OCR or manual entry)."""
    name: str
    score: int


class PlayerResultFull(TypedDict, total=False):
    """Extended player result with optional OCR metadata."""
    name: str
    score: int
    races: int
    raw_name: str
    embedded_score: int | None
    confidence: float


class ParsedOCRResult(TypedDict, total=False):
    """Complete OCR parse result from a single image."""
    results: list[PlayerResult]
    race_count: int
    warnings: list[str]
    raw_text: str
    table_format: str


# =============================================================================
# War Types
# =============================================================================

class WarRecord(TypedDict, total=False):
    """A war record as stored/retrieved from the database."""
    war_id: int
    guild_id: int
    race_count: int
    results: list[PlayerResult]
    timestamp: str
    team_score: int
    opponent_score: int
    team_differential: int


# =============================================================================
# Player Types
# =============================================================================

class PlayerStats(TypedDict, total=False):
    """Player statistics as returned by stats queries."""
    player_name: str
    total_score: int
    total_races: int
    war_count: int
    average_score: float
    highest_score: int
    lowest_score: int
    total_team_differential: int
    win_count: int
    loss_count: int
    win_percentage: float
    avg10_score: float | None
    hotstreak: float | None
    consistency_score: float | None
    clutch_factor: float | None
    form_score: float | None
    potential: float | None
    country_code: str | None
    team_name: str | None
    member_status: str | None
    last_war_date: str | None


class GuildConfig(TypedDict, total=False):
    """Guild configuration record."""
    guild_id: int
    guild_name: str
    team_names: list[str]
    is_active: bool
    ocr_channel_id: int | None


# =============================================================================
# Dataclasses for Computed Values
# =============================================================================

@dataclass
class TeamDifferential:
    """Computed team differential for a war."""
    team_score: int
    opponent_score: int
    differential: int

    @classmethod
    def from_results(
        cls,
        results: list[PlayerResult],
        race_count: int,
    ) -> TeamDifferential:
        """Calculate team differential from player results and race count.

        Uses TOTAL_POINTS_PER_RACE (82) * race_count for total possible points.
        """
        if race_count <= 0:
            raise ValueError(f"race_count must be positive, got {race_count}")
        from .constants import TOTAL_POINTS_PER_RACE
        team_score = sum(r["score"] for r in results)
        total_points = TOTAL_POINTS_PER_RACE * race_count
        opponent_score = total_points - team_score
        return cls(
            team_score=team_score,
            opponent_score=opponent_score,
            differential=team_score - opponent_score,
        )


@dataclass
class WarSubmissionResult:
    """Result of a war submission attempt through WarService."""
    success: bool
    war_id: int | None = None
    error_message: str | None = None
    is_duplicate: bool = False
    resolved_results: list[dict[str, Any]] = field(default_factory=list)
    team_score: int = 0
    opponent_score: int = 0
    differential: int = 0
