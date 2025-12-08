"""
MKW Stats Dashboard API
FastAPI backend for the MKW Stats Bot dashboard
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import DatabaseManager
from app.routes import auth, guild, players, wars, stats, bulk

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database manager instance
db: DatabaseManager = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle - startup and shutdown."""
    global db

    # Startup
    logger.info("Starting MKW Dashboard API...")
    db = DatabaseManager()
    app.state.db = db
    logger.info("Database connection pool initialized")

    yield

    # Shutdown
    logger.info("Shutting down MKW Dashboard API...")
    if db and db.connection_pool:
        db.connection_pool.closeall()
        logger.info("Database connections closed")


# Create FastAPI app
app = FastAPI(
    title="MKW Stats Dashboard API",
    description="API for the Mario Kart Wii Stats Bot Dashboard",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(guild.router, prefix="/api/guilds", tags=["Guilds"])
app.include_router(players.router, prefix="/api/guilds/{guild_id}/players", tags=["Players"])
app.include_router(wars.router, prefix="/api/guilds/{guild_id}/wars", tags=["Wars"])
app.include_router(stats.router, prefix="/api/guilds/{guild_id}/stats", tags=["Statistics"])
app.include_router(bulk.router, prefix="/api/bulk", tags=["Bulk Review"])


@app.get("/health")
async def health_check():
    """Health check endpoint for Railway."""
    return {"status": "healthy", "service": "mkw-dashboard-api"}


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "name": "MKW Stats Dashboard API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=settings.debug
    )
