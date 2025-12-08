"""
Dashboard API client for the MKW Stats Bot.
Handles communication with the FastAPI dashboard service.
"""
import aiohttp
import logging
from typing import List, Dict, Optional
from datetime import datetime

from .config import DASHBOARD_API_URL, DASHBOARD_API_KEY, DASHBOARD_WEB_URL, DASHBOARD_ENABLED

logger = logging.getLogger(__name__)


class DashboardClient:
    """Client for communicating with the Dashboard API."""

    def __init__(self):
        self.api_url = DASHBOARD_API_URL
        self.api_key = DASHBOARD_API_KEY
        self.web_url = DASHBOARD_WEB_URL
        self.enabled = DASHBOARD_ENABLED

    def is_enabled(self) -> bool:
        """Check if dashboard integration is enabled and configured."""
        return self.enabled and self.api_url and self.web_url

    def _get_headers(self) -> Dict[str, str]:
        """Get headers for API requests."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    async def create_bulk_session(
        self,
        guild_id: int,
        user_id: int,
        results: List[Dict]
    ) -> Optional[Dict]:
        """
        Create a bulk scan session in the dashboard API.

        Args:
            guild_id: Discord guild ID
            user_id: Discord user ID who initiated the scan
            results: List of OCR results, each containing:
                - filename: Image filename
                - image_url: URL to the image (optional)
                - players: List of detected players with scores
                - race_count: Number of races
                - message_timestamp: When the image was posted
                - discord_message_id: Discord message ID

        Returns:
            Dict with session info including 'token' for the review URL
        """
        if not self.is_enabled():
            logger.warning("Dashboard integration not enabled or configured")
            return None

        try:
            # Format results for the API
            formatted_results = []
            for result in results:
                formatted_results.append({
                    "filename": result.get("filename"),
                    "image_url": result.get("image_url"),
                    "players": [
                        {
                            "name": p.get("name", "Unknown"),
                            "score": p.get("score", 0),
                            "raw_name": p.get("raw_name") or p.get("original_name"),
                            "is_roster_member": p.get("is_roster_member", False),
                            "races_played": p.get("races_played", 12)
                        }
                        for p in result.get("players", [])
                    ],
                    "race_count": result.get("race_count", 12),
                    "message_timestamp": result.get("message_timestamp"),
                    "discord_message_id": result.get("discord_message_id")
                })

            payload = {
                "guild_id": guild_id,
                "user_id": user_id,
                "results": formatted_results
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/api/bulk/sessions",
                    json=payload,
                    headers=self._get_headers()
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"Created bulk session: {data.get('token')}")
                        return data
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to create bulk session: {response.status} - {error_text}")
                        return None

        except Exception as e:
            logger.error(f"Error creating bulk session: {e}")
            return None

    def get_review_url(self, token: str) -> str:
        """Get the full URL for reviewing a bulk scan session."""
        return f"{self.web_url}/review/{token}"

    async def check_health(self) -> bool:
        """Check if the dashboard API is reachable."""
        if not self.api_url:
            return False

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.api_url}/health",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    return response.status == 200
        except Exception as e:
            logger.error(f"Dashboard health check failed: {e}")
            return False


# Global client instance
dashboard_client = DashboardClient()
