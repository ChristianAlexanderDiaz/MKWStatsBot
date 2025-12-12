"""Bulk scan review routes for the MKW Dashboard API."""
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import logging

from app.config import settings
from app.database import DatabaseManager

logger = logging.getLogger(__name__)
router = APIRouter()


class PlayerResult(BaseModel):
    name: str
    score: int
    raw_name: Optional[str] = None
    is_roster_member: bool = False
    races_played: int = 12


class BulkScanResult(BaseModel):
    filename: Optional[str] = None
    image_url: Optional[str] = None
    players: List[PlayerResult]
    race_count: int = 12
    message_timestamp: Optional[str] = None
    discord_message_id: Optional[int] = None


class FailedScanResult(BaseModel):
    filename: Optional[str] = None
    image_url: Optional[str] = None
    error_message: str
    message_timestamp: Optional[str] = None
    discord_message_id: Optional[int] = None


class CreateSessionRequest(BaseModel):
    guild_id: int
    user_id: int
    results: List[BulkScanResult]
    failed_results: List[FailedScanResult] = []


class UpdateResultRequest(BaseModel):
    review_status: str  # pending, approved, rejected
    corrected_players: Optional[List[PlayerResult]] = None


def get_db(request: Request) -> DatabaseManager:
    """Get database from app state."""
    return request.app.state.db


def verify_api_key(x_api_key: Optional[str] = Header(None)):
    """Verify API key for bot -> API communication."""
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return True


@router.post("/sessions")
async def create_session(
    request_data: CreateSessionRequest,
    db: DatabaseManager = Depends(get_db),
    _: bool = Depends(verify_api_key)
):
    """Create a new bulk scan session (called by bot)."""
    results = [r.model_dump() for r in request_data.results]
    failed_results = [r.model_dump() for r in request_data.failed_results] if request_data.failed_results else None

    session = db.create_bulk_session(
        guild_id=request_data.guild_id,
        user_id=request_data.user_id,
        results=results,
        failed_results=failed_results
    )

    if not session:
        raise HTTPException(status_code=500, detail="Failed to create session")

    return session


@router.get("/sessions/{token}")
async def get_session(token: str, db: DatabaseManager = Depends(get_db)):
    """Get bulk scan session details."""
    session = db.get_bulk_session(token)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if "error" in session:
        raise HTTPException(status_code=410, detail=session["error"])

    return session


@router.get("/sessions/{token}/results")
async def get_session_results(token: str, db: DatabaseManager = Depends(get_db)):
    """Get all results for a bulk scan session."""
    # Verify session exists
    session = db.get_bulk_session(token)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if "error" in session:
        raise HTTPException(status_code=410, detail=session["error"])

    results = db.get_bulk_results(token)
    failures = db.get_bulk_failures(token)
    return {
        "session": session,
        "results": results,
        "failures": failures,
        "total": len(results)
    }


@router.put("/sessions/{token}/results/{result_id}")
async def update_result(
    token: str,
    result_id: int,
    update: UpdateResultRequest,
    db: DatabaseManager = Depends(get_db)
):
    """Update a single bulk scan result."""
    # Verify session exists
    session = db.get_bulk_session(token)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if update.review_status not in ["pending", "approved", "rejected"]:
        raise HTTPException(status_code=400, detail="Invalid review status")

    corrected = None
    if update.corrected_players:
        corrected = [p.model_dump() for p in update.corrected_players]

    success = db.update_bulk_result(result_id, update.review_status, corrected)
    if not success:
        raise HTTPException(status_code=404, detail="Result not found")

    return {"status": "success"}


@router.post("/sessions/{token}/failures/{failure_id}/convert")
async def convert_failure_to_result(
    token: str,
    failure_id: int,
    update: UpdateResultRequest,
    db: DatabaseManager = Depends(get_db)
):
    """Convert a failed scan to a result with manually entered players."""
    session = db.get_bulk_session(token)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Allow empty players only for rejections
    if not update.corrected_players and update.review_status != "rejected":
        raise HTTPException(status_code=400, detail="Players required")

    players = [p.model_dump() for p in update.corrected_players] if update.corrected_players else []
    result = db.convert_failure_to_result(failure_id, players, update.review_status)

    if not result:
        raise HTTPException(status_code=404, detail="Failure not found")

    return result


@router.post("/sessions/{token}/confirm")
async def confirm_session(token: str, db: DatabaseManager = Depends(get_db)):
    """Confirm and save all approved wars from a bulk scan session."""
    session = db.get_bulk_session(token)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if "error" in session:
        raise HTTPException(status_code=410, detail=session["error"])

    guild_id = session["guild_id"]
    results = db.get_bulk_results(token)

    # Save approved results as wars
    created_wars = []
    for result in results:
        if result["review_status"] == "approved":
            # Use corrected players if available, otherwise detected
            players = result["corrected_players"] or result["detected_players"]
            race_count = result["race_count"] or 12
            war_id = db.add_war(guild_id, players, race_count)

            if war_id:
                created_wars.append(war_id)

                # Calculate team differential
                team_score = sum(p.get('score', 0) for p in players)
                breakeven = 41 * race_count
                team_differential = team_score - breakeven

                # Update player stats and add war performance for each player
                war_date = datetime.now().strftime('%Y-%m-%d')
                for player in players:
                    player_name = player.get('name')
                    score = player.get('score', 0)
                    races_played = player.get('races_played', race_count)
                    war_participation = races_played / race_count if race_count > 0 else 1.0

                    # Add player war performance record
                    db.add_player_war_performance(
                        player_name=player_name,
                        war_id=war_id,
                        score=score,
                        races_played=races_played,
                        race_count=race_count,
                        guild_id=guild_id
                    )

                    # Update player statistics
                    db.update_player_stats(
                        player_name=player_name,
                        score=score,
                        races_played=races_played,
                        war_participation=war_participation,
                        war_date=war_date,
                        guild_id=guild_id,
                        team_differential=team_differential
                    )

    # Mark session as completed
    db.complete_bulk_session(token)

    return {
        "status": "success",
        "wars_created": len(created_wars),
        "war_ids": created_wars
    }


@router.post("/sessions/{token}/cancel")
async def cancel_session(token: str, db: DatabaseManager = Depends(get_db)):
    """Cancel a bulk scan session."""
    session = db.get_bulk_session(token)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Update status to cancelled
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE bulk_scan_sessions
                SET status = 'cancelled'
                WHERE token = %s
            """, (token,))
            conn.commit()
    except Exception as e:
        logger.error(f"Error cancelling session: {e}")
        raise HTTPException(status_code=500, detail="Failed to cancel session")

    return {"status": "cancelled"}
