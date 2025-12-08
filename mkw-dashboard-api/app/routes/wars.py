"""War routes for the MKW Dashboard API."""
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel
from typing import List, Optional
import logging

from app.database import DatabaseManager

logger = logging.getLogger(__name__)
router = APIRouter()


class PlayerResult(BaseModel):
    name: str
    score: int
    races_played: int = 12


class CreateWarRequest(BaseModel):
    results: List[PlayerResult]
    race_count: int = 12


def get_db(request: Request) -> DatabaseManager:
    """Get database from app state."""
    return request.app.state.db


@router.get("")
async def list_wars(
    guild_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: DatabaseManager = Depends(get_db)
):
    """Get paginated list of wars for a guild."""
    offset = (page - 1) * limit
    wars = db.get_wars(guild_id, limit=limit, offset=offset)
    total = db.get_war_count(guild_id)

    return {
        "wars": wars,
        "page": page,
        "limit": limit,
        "total": total,
        "pages": (total + limit - 1) // limit
    }


@router.post("")
async def create_war(
    guild_id: int,
    war: CreateWarRequest,
    db: DatabaseManager = Depends(get_db)
):
    """Create a new war."""
    results = [r.model_dump() for r in war.results]
    war_id = db.add_war(guild_id, results, war.race_count)

    if not war_id:
        raise HTTPException(status_code=500, detail="Failed to create war")

    return {"status": "success", "war_id": war_id}


@router.get("/{war_id}")
async def get_war(guild_id: int, war_id: int, db: DatabaseManager = Depends(get_db)):
    """Get details for a specific war."""
    wars = db.get_wars(guild_id, limit=1000, offset=0)

    # Find the specific war
    for war in wars:
        if war["id"] == war_id:
            return war

    raise HTTPException(status_code=404, detail="War not found")
