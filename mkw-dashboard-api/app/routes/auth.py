"""Authentication routes for Discord OAuth."""
from fastapi import APIRouter, Depends, HTTPException, Response, Request
from fastapi.responses import RedirectResponse
import httpx
import logging
from typing import Optional

from app.config import settings, DISCORD_API_BASE, DISCORD_OAUTH_AUTHORIZE, DISCORD_OAUTH_TOKEN, DISCORD_OAUTH_SCOPES
from app.database import DatabaseManager

logger = logging.getLogger(__name__)
router = APIRouter()


def get_db(request: Request) -> DatabaseManager:
    """Get database from app state."""
    return request.app.state.db


@router.get("/discord")
async def discord_login():
    """Redirect to Discord OAuth authorization page."""
    params = {
        "client_id": settings.discord_client_id,
        "redirect_uri": settings.discord_redirect_uri,
        "response_type": "code",
        "scope": " ".join(DISCORD_OAUTH_SCOPES)
    }
    query_string = "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(f"{DISCORD_OAUTH_AUTHORIZE}?{query_string}")


@router.get("/callback")
async def discord_callback(code: str, request: Request, db: DatabaseManager = Depends(get_db)):
    """Handle Discord OAuth callback."""
    if not code:
        raise HTTPException(status_code=400, detail="No code provided")

    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            DISCORD_OAUTH_TOKEN,
            data={
                "client_id": settings.discord_client_id,
                "client_secret": settings.discord_client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.discord_redirect_uri
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        if token_response.status_code != 200:
            logger.error(f"Token exchange failed: {token_response.text}")
            raise HTTPException(status_code=400, detail="Failed to exchange code for token")

        tokens = token_response.json()
        access_token = tokens["access_token"]

        # Get user info
        user_response = await client.get(
            f"{DISCORD_API_BASE}/users/@me",
            headers={"Authorization": f"Bearer {access_token}"}
        )

        if user_response.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to get user info")

        user_data = user_response.json()

        # Get user's guilds
        guilds_response = await client.get(
            f"{DISCORD_API_BASE}/users/@me/guilds",
            headers={"Authorization": f"Bearer {access_token}"}
        )

        guilds = guilds_response.json() if guilds_response.status_code == 200 else []

        # Build guild permissions (simplified - check if user is admin/owner)
        guild_permissions = {}
        for guild in guilds:
            permissions = guild.get("permissions", 0)
            is_owner = guild.get("owner", False)
            is_admin = (permissions & 0x8) == 0x8  # ADMINISTRATOR permission

            if is_owner or is_admin:
                guild_permissions[str(guild["id"])] = {
                    "is_admin": True,
                    "can_manage": True,
                    "guild_name": guild["name"]
                }
            elif (permissions & 0x20) == 0x20:  # MANAGE_GUILD permission
                guild_permissions[str(guild["id"])] = {
                    "is_admin": False,
                    "can_manage": True,
                    "guild_name": guild["name"]
                }

        # Create session
        session_token = db.create_user_session(
            discord_user_id=int(user_data["id"]),
            discord_username=user_data["username"],
            discord_avatar=user_data.get("avatar"),
            guild_permissions=guild_permissions
        )

        if not session_token:
            raise HTTPException(status_code=500, detail="Failed to create session")

        # Redirect to frontend with session token
        redirect_url = f"{settings.frontend_url}/auth/callback?token={session_token}"
        return RedirectResponse(redirect_url)


@router.get("/me")
async def get_current_user(
    request: Request,
    db: DatabaseManager = Depends(get_db)
):
    """Get current user info from session token."""
    # Get token from Authorization header or cookie
    auth_header = request.headers.get("Authorization", "")
    token = None

    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    else:
        token = request.cookies.get("session_token")

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    session = db.get_user_session(token)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    return {
        "id": session["discord_user_id"],
        "username": session["discord_username"],
        "avatar": session["discord_avatar"],
        "guilds": session["guild_permissions"]
    }


@router.post("/logout")
async def logout(
    request: Request,
    db: DatabaseManager = Depends(get_db)
):
    """Logout and invalidate session."""
    auth_header = request.headers.get("Authorization", "")
    token = None

    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    else:
        token = request.cookies.get("session_token")

    if token:
        db.delete_user_session(token)

    return {"status": "logged out"}
