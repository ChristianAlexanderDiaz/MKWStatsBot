"""Guild routes for the MKW Dashboard API."""
from fastapi import APIRouter, Depends, HTTPException, Request
from typing import List, Optional
import logging

from app.database import DatabaseManager

logger = logging.getLogger(__name__)
router = APIRouter()


def get_db(request: Request) -> DatabaseManager:
    """Get database from app state."""
    return request.app.state.db


@router.get("")
async def list_guilds(request: Request, db: DatabaseManager = Depends(get_db)):
    """List guilds the user has access to (from session)."""
    # Get session token
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else request.cookies.get("session_token")

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    session = db.get_user_session(token)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    # Return guilds from session permissions
    guilds = []
    for guild_id, perms in session.get("guild_permissions", {}).items():
        config = db.get_guild_config(int(guild_id))
        guilds.append({
            "id": guild_id,
            "name": perms.get("guild_name", f"Guild {guild_id}"),
            "is_admin": perms.get("is_admin", False),
            "can_manage": perms.get("can_manage", False),
            "is_configured": config is not None
        })

    return guilds


@router.get("/{guild_id}")
async def get_guild(guild_id: int, db: DatabaseManager = Depends(get_db)):
    """Get guild details and configuration."""
    config = db.get_guild_config(guild_id)
    overview = db.get_guild_overview(guild_id)

    return {
        "id": guild_id,
        "config": config,
        "overview": overview
    }


@router.get("/{guild_id}/teams")
async def get_guild_teams(guild_id: int, db: DatabaseManager = Depends(get_db)):
    """Get teams for a guild."""
    teams = db.get_teams(guild_id)
    return {"teams": teams}
