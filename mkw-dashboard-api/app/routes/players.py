"""Player routes for the MKW Dashboard API."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import List, Optional
import logging

from app.database import DatabaseManager

logger = logging.getLogger(__name__)
router = APIRouter()


class AddPlayerRequest(BaseModel):
    name: str
    member_status: str = "member"


class UpdateStatusRequest(BaseModel):
    member_status: str


class AddNicknameRequest(BaseModel):
    nickname: str


def get_db(request: Request) -> DatabaseManager:
    """Get database from app state."""
    return request.app.state.db


@router.get("")
async def list_players(guild_id: int, db: DatabaseManager = Depends(get_db)):
    """Get all players in a guild's roster."""
    players = db.get_roster_players(guild_id)
    return {"players": players, "total": len(players)}


@router.post("")
async def add_player(
    guild_id: int,
    player: AddPlayerRequest,
    db: DatabaseManager = Depends(get_db)
):
    """Add a new player to the roster."""
    if player.member_status not in ["member", "trial", "ally", "kicked"]:
        raise HTTPException(status_code=400, detail="Invalid member status")

    success = db.add_player(
        player_name=player.name,
        guild_id=guild_id,
        member_status=player.member_status
    )

    if not success:
        raise HTTPException(status_code=400, detail="Player already exists or failed to add")

    return {"status": "success", "player": player.name}


@router.get("/{player_name}")
async def get_player(guild_id: int, player_name: str, db: DatabaseManager = Depends(get_db)):
    """Get details for a specific player."""
    stats = db.get_player_stats(player_name, guild_id)
    if not stats:
        raise HTTPException(status_code=404, detail="Player not found")
    return stats


@router.put("/{player_name}/status")
async def update_player_status(
    guild_id: int,
    player_name: str,
    status_update: UpdateStatusRequest,
    db: DatabaseManager = Depends(get_db)
):
    """Update a player's member status."""
    if status_update.member_status not in ["member", "trial", "ally", "kicked"]:
        raise HTTPException(status_code=400, detail="Invalid member status")

    success = db.update_player_status(player_name, guild_id, status_update.member_status)
    if not success:
        raise HTTPException(status_code=404, detail="Player not found")

    return {"status": "success", "new_status": status_update.member_status}


@router.post("/{player_name}/nicknames")
async def add_player_nickname(
    guild_id: int,
    player_name: str,
    nickname_request: AddNicknameRequest,
    db: DatabaseManager = Depends(get_db)
):
    """Add a nickname to a player."""
    success = db.add_nickname(player_name, guild_id, nickname_request.nickname)
    if not success:
        raise HTTPException(status_code=404, detail="Player not found or nickname add failed")

    return {"status": "success", "nickname": nickname_request.nickname}
