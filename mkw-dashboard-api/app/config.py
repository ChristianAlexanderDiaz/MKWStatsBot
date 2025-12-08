"""
Configuration management for MKW Dashboard API.
Loads settings from environment variables.
"""
import os
from typing import List

from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Server settings
    port: int = int(os.getenv("PORT", "8000"))
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Database
    database_url: str = os.getenv(
        "DATABASE_URL",
        os.getenv("DATABASE_PUBLIC_URL", "")
    )

    # Discord OAuth
    discord_client_id: str = os.getenv("DISCORD_CLIENT_ID", "")
    discord_client_secret: str = os.getenv("DISCORD_CLIENT_SECRET", "")
    discord_redirect_uri: str = os.getenv(
        "DISCORD_REDIRECT_URI",
        "http://localhost:8000/api/auth/callback"
    )

    # JWT settings
    jwt_secret: str = os.getenv("JWT_SECRET", "change-me-in-production")
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 168  # 7 days

    # Frontend URL (for redirects after OAuth)
    frontend_url: str = os.getenv("FRONTEND_URL", "http://localhost:3000")

    # CORS origins
    @property
    def cors_origins(self) -> List[str]:
        origins = os.getenv("CORS_ORIGINS", self.frontend_url)
        if "," in origins:
            return [o.strip() for o in origins.split(",")]
        return [origins]

    # API key for bot -> API communication
    api_key: str = os.getenv("API_KEY", "")

    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()


# Discord OAuth URLs
DISCORD_API_BASE = "https://discord.com/api/v10"
DISCORD_OAUTH_AUTHORIZE = "https://discord.com/api/oauth2/authorize"
DISCORD_OAUTH_TOKEN = "https://discord.com/api/oauth2/token"
DISCORD_OAUTH_REVOKE = "https://discord.com/api/oauth2/token/revoke"

# OAuth scopes needed
DISCORD_OAUTH_SCOPES = ["identify", "guilds"]
