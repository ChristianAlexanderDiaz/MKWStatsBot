"""Statistics routes for the MKW Dashboard API."""
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from typing import Optional
import logging

from app.database import DatabaseManager

logger = logging.getLogger(__name__)
router = APIRouter()


def get_db(request: Request) -> DatabaseManager:
    """Get database from app state."""
    return request.app.state.db


@router.get("/overview")
async def get_overview(guild_id: int, db: DatabaseManager = Depends(get_db)):
    """Get guild statistics overview."""
    overview = db.get_guild_overview(guild_id)
    return overview


@router.get("/leaderboard")
async def get_leaderboard(
    guild_id: int,
    sort: str = Query("average_score", regex="^(average_score|total_score|war_count|total_team_differential)$"),
    limit: int = Query(50, ge=1, le=100),
    db: DatabaseManager = Depends(get_db)
):
    """Get leaderboard sorted by specified field."""
    leaderboard = db.get_leaderboard(guild_id, sort_by=sort, limit=limit)
    return {"leaderboard": leaderboard, "sort_by": sort}


@router.get("/player/{player_name}")
async def get_player_stats(
    guild_id: int,
    player_name: str,
    db: DatabaseManager = Depends(get_db)
):
    """Get detailed stats for a specific player."""
    stats = db.get_player_stats(player_name, guild_id)
    if not stats:
        raise HTTPException(status_code=404, detail="Player not found")
    return stats
