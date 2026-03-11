# MKW Stats Bot - Development Guide

## Project Overview
Full-stack Discord bot for Mario Kart clan stats with OCR and web dashboard.
- **Stack**: Python (discord.py) + FastAPI + Next.js 15 + PostgreSQL + PaddleOCR
- **Deployment**: Railway with Docker, multi-service architecture
- **Multi-Guild**: Full data isolation between Discord servers

## Architecture (post-refactor)

```
mkw_stats/
    bot.py                      # ~420 lines — MarioKartBot, event routing, handler wiring
    database.py                 # ~390 lines — DatabaseManager, connection pool, schema init
    config.py                   # Bot configuration
    constants.py                # All magic numbers, score ranges, sort definitions
    types.py                    # Shared TypedDicts and dataclasses (PlayerResult, WarData, etc.)
    ocr_processor.py            # ~400 lines — OCR orchestration
    ocr_config_manager.py       # OCR tuning configuration
    ocr_modals.py               # Discord UI modals for OCR correction
    ocr_performance_monitor.py  # OCR metrics
    ocr_resource_manager.py     # OCR concurrency management
    dashboard_client.py         # HTTP client to dashboard API
    logging_config.py           # Logging setup
    cogs/                       # 8 slash-command domain cogs
        base_cog.py             # BaseCog, shared decorators (require_guild_setup, etc.)
        guild_cog.py            # /setup, /setchannel, /setroles, /help, /send
        player_cog.py           # /addplayer, /removeplayer, /linkplayer, /roster, /syncstatus
        war_cog.py              # /addwar, /removewar, /showallwars, /appendplayer
        stats_cog.py            # /stats, /leaderboard
        team_cog.py             # /assignplayers, /showteams, /addteam, /removeteam, team tags
        nickname_cog.py         # /addnickname, /removenickname, /nicknamesfor
        member_cog.py           # /setmemberstatus, /showtrials, /showkicked
        ocr_cog.py              # /scanimage, /bulkscanimage, /debugocr
    handlers/                   # Bot event and message handlers
        ocr_handler.py          # Auto-OCR image processing, war submission from views
        bulk_scan_handler.py    # Bulk scan orchestration, dashboard session creation
        confirmation_manager.py # Pending confirmation state, timeout tasks
        message_manager.py      # Auto-delete, countdown messages
    repositories/               # Database access layer
        player_repository.py    # All player CRUD, nickname ops, Discord linking
        war_repository.py       # War CRUD, duplicate detection
        stats_repository.py     # Statistics, form scores, volatile metrics
        guild_repository.py     # Guild config, teams, roles, OCR channel
    services/                   # Business logic layer
        war_service.py          # Single entry point for war submission (deduplicates 3 flows)
        player_service.py       # Player add/remove/link/status
        guild_service.py        # Guild setup, role config, team management
    utils/
        embed_builder.py        # EmbedBuilder with static factory methods
        validators.py           # Input validation helpers
        formatters.py           # country_code_to_flag, format_error_for_user, etc.
    ocr/                        # OCR sub-modules
        name_resolver.py        # NameResolver — window-based name matching
        score_pairer.py         # ScorePairer — bbox-based name/score pairing
        team_splitter.py        # TeamSplitter — 6v6 team identification
```

## Database Access Pattern
All DB calls are **async** (asyncpg). Repositories are accessed via `await self.bot.db.REPO.method()` in cogs and handlers:
```python
await self.bot.db.players.resolve_player_name(name, guild_id)
await self.bot.db.wars.add_race_results(results, guild_id=guild_id)
await self.bot.db.stats.get_player_stats(player_name, guild_id)
await self.bot.db.guilds.get_guild_config(guild_id)
```
Connection pool access: `async with self.bot.db.get_connection() as conn:` (async context manager).

## Critical Patterns

### Python Standards
- **Indentation**: 4 spaces, type hints required, async for Discord ops
- **Database**: Use repository pattern via `db.players.x`, `db.wars.x`, `db.stats.x`, `db.guilds.x`
- **Guild Isolation**: All DB methods accept `guild_id` parameter

### Database Schema (Multi-Guild)
- `players`: guild_id, nicknames (JSONB), team assignments
- `wars`: guild_id, player results
- `guild_configs`: per-guild settings, team names, channels

## Key Commands
**Essential Dev**: `python main.py`, `python admin/setup_players.py`, `python admin/check_database.py`

**Slash Commands (40+ total):**
- `/setup` - Initialize guild (required first step)
- `/setchannel` - Set auto-OCR channel
- `/addwar`, `/removewar`, `/showallwars`, `/appendplayer` - War management
- `/stats [player] [lastxwars] [sortby]`, `/leaderboard` - Statistics
- `/roster`, `/addplayer`, `/removeplayer`, `/linkplayer` - Player management
- `/addteam`, `/assignplayers`, `/showteams`, `/showteamroster` - Team management
- `/addnickname`, `/removenickname`, `/nicknamesfor` - Nickname management for OCR
- `/setmemberstatus`, `/showtrials`, `/showkicked` - Member status tracking
- `/scanimage`, `/bulkscanimage`, `/debugocr` - OCR tools

## OCR Workflow
**Auto-OCR**: PNG uploads to configured channel → PaddleOCR extracts → validate → ✅/❌ confirm
**Bulk**: `/bulkscanimage` → scans channel → web dashboard review URL → approve all at once
**Manual**: `/scanimage` (backup if auto-OCR misses)

## Web Dashboard
`mkw-dashboard-api/` (FastAPI) + `mkw-review-web/` (Next.js 15)
- `mkw-review-web/src/hooks/useBulkReview.ts` — all bulk review state and handlers
- `mkw-review-web/src/components/review/` — WarResultCard, FailureCard, ReviewHeader, etc.
- Discord OAuth auth, edit wars at once, approve/reject/edit OCR results

## Environment Variables
- `DISCORD_BOT_TOKEN` (required)
- `DATABASE_URL` (Railway auto-configures)
- OCR optimization: `OCR_MODE` (balanced/bulk_heavy/single_focused), `OCR_MAX_CONCURRENT`, `OCR_PADDLE_CPU_THREADS`

## Development Guidelines
- Read existing files before proposing changes
- Test DB changes with `admin/check_database.py`
- Test OCR with `testing/sample_images/`
- Add new slash commands to the appropriate cog in `cogs/`
- Use Black (line-length 88), mypy strict mode, pytest
