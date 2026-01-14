# MKW Stats Bot - Development Guide

## Project Overview
Full-stack Discord bot for Mario Kart clan stats with OCR and web dashboard.
- **Stack**: Python (discord.py) + FastAPI + Next.js 15 + PostgreSQL + PaddleOCR
- **Deployment**: Railway with Docker, multi-service architecture
- **Multi-Guild**: Full data isolation between Discord servers

## Core File Structure
- `mkw_stats/bot.py`: Main Discord bot (MarioKartBot)
- `mkw_stats/commands.py`: All slash commands (MarioKartCommands cog)
- `mkw_stats/database.py`: PostgreSQL manager with connection pooling
- `mkw_stats/ocr_processor.py`: Image processing and OCR
- `admin/setup_players.py`: Initialize database
- `testing/test_ocr.py`, `test_database.py`: Testing utilities

## Critical Patterns

### Python Standards
- **Indentation**: 4 spaces, type hints required, async for Discord ops
- **Database**: Always use `self.db.connection_pool`, context managers, JSONB for complex data
- **Guild Isolation**: All DB methods accept `guild_id` parameter

### Database Schema (Multi-Guild)
- `players`: guild_id, nicknames (JSONB), team assignments
- `wars`: guild_id, player results
- `guild_configs`: per-guild settings, team names, channels

## Key Commands
**Essential Dev**: `python main.py`, `python admin/setup_players.py`, `python admin/check_database.py`

**Slash Commands** (25+ total):
- `/setup` - Initialize guild (required first step)
- `/setchannel` - Set auto-OCR channel
- `/addwar`, `/removewar`, `/showallwars` - War management
- `/stats [player] [lastxwars] [sortby]` - Statistics/leaderboard
- `/roster`, `/addplayer`, `/removeplayer` - Player management
- `/addteam`, `/assignplayers`, `/showallteams` - Team management
- `/addnickname`, `/nicknamesfor` - Nickname management for OCR
- `/setmemberstatus`, `/showtrials` - Member status tracking

## OCR Workflow
**Auto-OCR**: PNG uploads to configured channel → PaddleOCR extracts → validate → ✅/❌ confirm
**Bulk**: `/bulkscanimage` → scans channel → web dashboard review URL → approve all at once
**Manual**: `/scanimage` (backup if auto-OCR misses)

## Web Dashboard
`mkw-dashboard-api/` (FastAPI) + `mkw-review-web/` (Next.js)
- Discord OAuth auth, edit 70+ wars at once, approve/reject

## Environment Variables
- `DISCORD_BOT_TOKEN` (required)
- `DATABASE_URL` (Railway auto-configures)
- OCR optimization: `OCR_MODE` (balanced/bulk_heavy/single_focused), `OCR_MAX_CONCURRENT`, `OCR_PADDLE_CPU_THREADS`

## Development Guidelines
- Read existing files before proposing changes
- Test DB changes with `admin/check_database.py`
- Test OCR with `testing/sample_images/`
- Follow existing command patterns in `commands.py`
- Use Black (line-length 88), mypy strict mode, pytest
