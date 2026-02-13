"""
Shared type definitions for the MKW Stats Bot.

TypedDicts and dataclasses that flow between modules.
Keeps type information centralized to avoid circular imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict, Optional, List, Dict, Any


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
    embedded_score: Optional[int]
    confidence: float


class ParsedOCRResult(TypedDict, total=False):
    """Complete OCR parse result from a single image."""
    results: List[PlayerResult]
    race_count: int
    warnings: List[str]
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
    results: List[PlayerResult]
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
    war_count: float
    average_score: float
    highest_score: int
    lowest_score: int
    total_team_differential: int
    win_count: int
    loss_count: int
    win_percentage: float
    avg10_score: Optional[float]
    hotstreak: Optional[float]
    consistency_score: Optional[float]
    clutch_factor: Optional[float]
    form_score: Optional[float]
    potential: Optional[float]
    country_code: Optional[str]
    team_name: Optional[str]
    member_status: Optional[str]
    last_war_date: Optional[str]


class GuildConfig(TypedDict, total=False):
    """Guild configuration record."""
    guild_id: int
    guild_name: str
    team_names: List[str]
    is_active: bool
    ocr_channel_id: Optional[int]


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
    def from_results(cls, results: List[PlayerResult], race_count: int) -> TeamDifferential:
        """Calculate team differential from player results and race count.

        Uses TOTAL_POINTS_PER_RACE (82) * race_count for total possible points.
        """
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
    war_id: Optional[int] = None
    error_message: Optional[str] = None
    is_duplicate: bool = False
    resolved_results: List[Dict[str, Any]] = field(default_factory=list)
    team_score: int = 0
    opponent_score: int = 0
    differential: int = 0
