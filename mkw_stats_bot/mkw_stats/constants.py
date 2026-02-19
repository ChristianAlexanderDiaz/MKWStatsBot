"""
Centralized constants for the MKW Stats Bot.

All magic numbers, thresholds, and configuration constants live here
so they can be imported by any module without circular dependencies.
"""

from typing import Dict

# =============================================================================
# Bot Identity
# =============================================================================

BOT_OWNER_ID: int = 291621912914821120

# =============================================================================
# Database Connection
# =============================================================================

DB_POOL_MIN: int = 1
DB_POOL_MAX: int = 10
DB_CONNECT_TIMEOUT: int = 10
DB_STATEMENT_TIMEOUT: int = 30000  # milliseconds

# =============================================================================
# Form Score Calculation
# =============================================================================

FORM_SCORE_DECAY_FACTOR: float = 0.85  # Exponential weight decay (recent wars weighted ~15% more)
FORM_SCORE_MIN_WARS: int = 10  # Minimum wars required for Form Score calculation
FORM_AVERAGE_SCORE: int = 84  # Average score baseline for form rating
FORM_GOLDEN_SCORE: int = 100  # Golden score threshold
FORM_PERFECT_SCORE: int = 110  # Perfect score threshold

# =============================================================================
# Clutch Factor Thresholds (percentile-based)
# =============================================================================

CLOSE_WAR_THRESHOLD: int = 38  # abs(team_differential) <= 38 = close war
CLUTCH_ELITE_THRESHOLD: float = 0.45   # Top 10%
CLUTCH_POSITIVE_THRESHOLD: float = 0.14  # Next 15%
CLUTCH_NEUTRAL_THRESHOLD: float = -0.30  # Middle 50%
CLUTCH_SHAKY_THRESHOLD: float = -0.87   # Next 15%
# Below -0.87 = "Chokes" (bottom 10%)

# =============================================================================
# Game Rules / War Configuration
# =============================================================================

TOTAL_POINTS_PER_RACE: int = 82  # Sum of all 12 positions' points
SCORE_MIN_PER_RACE: int = 1
SCORE_MAX_PER_RACE: int = 15

# =============================================================================
# Discord UI
# =============================================================================

UNICODE_REGIONAL_INDICATOR_OFFSET: int = 127462  # For country flag conversion
LEADERBOARD_PLAYERS_PER_PAGE: int = 10
CONFIRMATION_VIEW_TIMEOUT: int = 300  # 5 minutes (discord.ui.View timeout)
QUICK_CONFIRM_TIMEOUT: int = 60  # 1 minute (reaction-based confirmations)
DEFAULT_COUNTDOWN_SECONDS: int = 30
ERROR_MSG_TRUNCATE_LENGTH: int = 150

# Embed colors
COLOR_SUCCESS: int = 0x00FF00
COLOR_ERROR: int = 0xFF4444
COLOR_WARNING: int = 0xFFA500
COLOR_INFO: int = 0x3498DB
COLOR_PURPLE: int = 0x9932CC
COLOR_DARK_EMBED: int = 0x2B2D31
COLOR_EXPIRED: int = 0x808080

# =============================================================================
# Sort Options (used by leaderboard views and stats commands)
# =============================================================================

SORT_DISPLAY_NAMES: Dict[str, str] = {
    "avg10": "Average 10",
    "avgdiff": "Average Team Differential",
    "clutch": "Clutch Factor",
    "cv": "Consistency",
    "form": "Form",
    "highest": "Highest Score",
    "hotstreak": "Hotstreak",
    "lastwar": "Last War",
    "lowest": "Lowest",
    "potential": "Potential",
    "totaldiff": "Total Differential",
    "warcount": "Number of Wars",
    "winrate": "Win Rate",
}

SORT_DESCRIPTIONS: Dict[str, str] = {
    "avg10": "Recent form - average of your last 10 wars. Shows current performance vs all-time average.",
    "avgdiff": "Team differential per war - how much your team wins/loses by on average. Positive = helping your team, negative = holding team back.",
    "clutch": "Clutch factor - performance in close wars (differential <=38) vs overall average. Categories: Elite Clutch (+0.45+), Clutch (+0.14 to +0.45), Neutral (-0.30 to +0.14), Shaky (-0.87 to -0.30), Chokes (-0.87 or lower).",
    "cv": "Consistency score (0-100%) - higher is more consistent. 90% = very steady, 50% = moderate variance, 0% = extremely inconsistent.",
    "form": "Soccer-style rating (0-10+) of recent performance. Exponentially weighted average of last 10-20 wars where recent matches count more heavily. 6.0=average, 9.0=excellent, 10.0+=elite.",
    "highest": "Personal best - the highest individual score you've ever achieved in a single war.",
    "hotstreak": "Average of last 10 wars minus your career average. Positive = hot streak (beating your average), negative = slump (below your average).",
    "lastwar": "Most recent war - sorts by date so you see who played most recently. Useful for finding active players.",
    "lowest": "Personal worst - the lowest individual score you've ever gotten in a single war.",
    "potential": "Performance ceiling - recent form (avg10) plus standard deviation. Estimates your upper capability range.",
    "totaldiff": "Career team differential - total points you've helped/hurt your team across all wars. Your impact on team success.",
    "warcount": "Experience level - total number of wars played. Higher = more experience.",
    "winrate": "Team win percentage - % of wars where your team won. Shows if you're on winning teams.",
}

# Global leaderboard title map
GLOBAL_SORT_TITLES: Dict[str, str] = {
    "avg": "Average Score",
    "avg10": "Average 10",
    "avgdiff": "Average Differential",
    "clutch": "Clutch Factor",
    "cv": "Consistency",
    "form": "Form",
    "highest": "Highest Score",
    "hotstreak": "Hotstreak",
    "lastwar": "Last War",
    "lowest": "Lowest Score",
    "potential": "Potential",
    "totaldiff": "Total Differential",
    "warcount": "War Count",
    "winrate": "Win Rate",
}

# =============================================================================
# Member Status
# =============================================================================

MEMBER_STATUSES = ["member", "trial", "ally", "kicked"]
