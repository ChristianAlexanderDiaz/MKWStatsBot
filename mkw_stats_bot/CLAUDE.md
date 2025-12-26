# MKW Stats Bot - Claude Development Guide

## Project Overview

- **Purpose**: Full-stack Discord bot ecosystem for Mario Kart clan statistics with OCR and web dashboard
- **Architecture**: Python Discord bot + FastAPI backend + Next.js frontend + PostgreSQL database + PaddleOCR
- **Version**: Production (actively deployed)
- **Deployment**: Railway with PostgreSQL, Docker support, multi-service architecture
- **Multi-Guild Support**: Full data isolation between Discord servers, unlimited guilds supported
- **Web Dashboard**: Next.js 15 with React Server Components, TypeScript, Tailwind CSS

## Core Technologies

- **Python**: 3.11+ required
- **Discord**: discord.py 2.0+ with message content and reactions intents
- **Database**: PostgreSQL with connection pooling (psycopg2-binary)
- **OCR**: Tesseract + OpenCV + pytesseract for image processing
- **Environment**: python-dotenv for configuration

## Development Commands

### Essential Commands

- **Start Bot**: `python main.py`
- **Database Setup**: `python admin/setup_players.py`
- **Check Database**: `python admin/check_database.py`
- **Test OCR**: `python testing/test_ocr.py`
- **Test Database**: `python testing/test_database.py`
- **Test Multi-Guild**: `python testing/test_multi_guild.py`

### Multi-Guild Migration

- **Apply Migration**: `python scripts/utilities/migrate_add_guild_support.py`
- **Test Multi-Guild**: `python testing/test_multi_guild.py`

### Code Quality

- **Linting**: Use Black (line-length 88), flake8, mypy as configured in pyproject.toml
- **Type Checking**: mypy with strict settings enabled
- **Testing**: pytest with coverage reporting

## Code Style & Conventions

### Python Standards

- **Indentation**: 4 spaces (not tabs)
- **Type Hints**: Required for all functions and methods
- **Async/Await**: Use async patterns for Discord operations
- **Error Handling**: Comprehensive try/catch with logging
- **Logging**: Use centralized logger from `logging_config.py`

### Database Operations

- **Connection Pooling**: Always use `self.db.connection_pool`
- **Context Managers**: Use `@contextmanager` for database connections
- **JSONB**: Store complex data (nicknames, score_history) as JSONB
- **Transactions**: Use proper transaction handling for data integrity
- **Guild Isolation**: All database methods accept guild_id parameter for data isolation

## Project Structure

### Core Application (`mkw_stats/`)

- `bot.py`: Main Discord bot class (MarioKartBot)
- `commands.py`: All Discord commands (MarioKartCommands cog)
- `database.py`: PostgreSQL database manager with connection pooling
- `ocr_processor.py`: Image processing and OCR functionality
- `config.py`: Configuration management and environment variables
- `logging_config.py`: Centralized logging setup

### Management Scripts (`admin/`)

- `setup_players.py`: Initialize player roster and database
- `check_database.py`: Database inspection and statistics
- `manage_nicknames.py`: Interactive nickname management
- `reset_database.py`: Database reset utility

### Testing (`testing/`)

- `test_database.py`: Database functionality tests
- `test_ocr.py`: OCR processing tests
- Sample images for testing OCR

## Multi-Guild Support

### Overview

The MKW Stats Bot supports multiple Discord guilds (servers) with complete data isolation. Each guild maintains:

- **Separate Player Rosters**: Players in Guild A cannot see players in Guild B
- **Isolated War Data**: Wars are tracked per guild with no cross-contamination
- **Independent Statistics**: Player statistics are calculated per guild
- **Custom Team Names**: Each guild can configure their own team names
- **Guild-Specific Settings**: Allowed channels, configurations per guild

### Database Schema

The multi-guild architecture uses `guild_id` columns across all core tables:

- **players**: Players are scoped to their guild_id (replaced old 'roster' table)
- **wars**: War sessions are isolated per guild_id
- **guild_configs**: Per-guild settings and configurations

**Note**: The database schema has been updated to use a single `players` table instead of separate `roster` and `player_stats` tables for improved data consistency and performance.

### Guild Management Commands

- **Setup**: `/setup` - Initialize guild configuration (slash command)
- **Configure**: `!mkguildconfig [action] [value]` - Manage guild settings
- **Information**: `!mkguildinfo` - View guild statistics and configuration
- **Team Names**: Configure custom team names per guild
- **Channel Restrictions**: Limit bot usage to specific channels

### Migration Process

1. **Run Migration**: `python scripts/utilities/migrate_add_guild_support.py`
2. **Existing Data**: Automatically migrated to default guild_id (0)
3. **Test Setup**: `python testing/test_multi_guild.py`
4. **Guild Setup**: Use `/setup` in each Discord server

### Guild Configuration Options

- **Guild Name**: Display name for the guild
- **Team Names**: Custom team names (default: none, configured via /setup)
- **Allowed Channels**: Restrict bot commands to specific channels
- **Active Status**: Enable/disable guild functionality

### Data Isolation

- **Complete Separation**: No data leakage between guilds
- **Independent Operations**: All commands scoped to current guild
- **Secure Architecture**: Guild ID extracted from Discord context
- **Database Constraints**: Foreign keys enforce guild-level isolation

## Discord Bot Architecture

### First-Time Guild Setup

**Required Command**: `/setup`

```
/setup teamname:YourTeam players:Player1,Player2,Player3 results_channel:#channel
```

This initializes:

- Guild configuration in `guild_configs` table
- First team with provided name
- Initial player roster (all assigned to the team)
- Sets the OCR channel for automatic image processing

**After Setup**: Use `/setchannel` to change the OCR channel:

```
/setchannel channel:#new-channel
```

### Automatic OCR Processing

Once the OCR channel is set (via `/setup` or `/setchannel`):

- Any PNG image uploaded to that channel is automatically scanned
- Bot processes images from Lorenzi's Game Boards or Ice Mario
- Shows confirmation UI with detected players and scores
- User clicks "Save War" button or ✅ reaction to approve
- No manual `/scanimage` command needed (that's a backup if auto-OCR misses)

### Command Structure (25+ slash commands total)

#### Slash Commands (/) - Primary Interface

- **Guild Setup**: `/setup <teamname> <players> <results_channel>` - Initialize guild configuration
- **Channel Management**: `/setchannel <channel>` - Set automatic OCR processing channel
- **War Management**:
  - `/addwar <player_scores> [races]` - Add new war with player scores (OCR optional)
  - `/showallwars [limit]` - List all wars with pagination
  - `/appendplayertowar <war_id> <player_scores>` - Add/update players to existing war (smart merge)
  - `/removewar <war_id>` - Delete war and revert player statistics (returns count of reverted players)
- **Statistics**: `/stats [player] [lastxwars] [sortby]` - View player statistics or leaderboard
  - Optional: `lastxwars` - Show stats for last X wars only (e.g., lastxwars:10)
  - Optional: `sortby` - Sort by: Average Score (default), Win Rate, Average Differential
- **Player Management**:
  - `/roster` - Show complete guild roster organized by teams
  - `/addplayer <player_name> [member_status]` - Add player to roster with optional status (Member/Trial/Ally/Kicked)
  - `/removeplayer <player_name>` - Remove player from roster
- **Team Management**:
  - `/addteam <team_name>` - Create new team
  - `/removeteam <team_name>` - Remove existing team
  - `/renameteam <old_name> <new_name>` - Rename team
  - `/assignplayers <players> <team_name>` - Assign players to team (1 or more, with autocomplete for players and teams)
  - `/unassignplayer <player_name>` - Set player to Unassigned (with autocomplete for players)
  - `/showallteams` - Show all teams and their players
  - `/showspecificteamroster <team_name>` - Show specific team roster
- **Nickname Management**:
  - `/addnickname <player_name> <nickname>` - Add nickname for OCR recognition
  - `/removenickname <player_name> <nickname>` - Remove nickname from player
  - `/nicknamesfor <player_name>` - Show all nicknames for player
- **Member Status Management**:
  - `/setmemberstatus <player_name> <status>` - Set player status (Member/Trial/Ally/Kicked)
  - `/showtrials` - Show all trial members
  - `/showkicked` - Show all kicked members
- **Help**: `/help` - Show comprehensive bot help and command reference

#### Legacy Commands Removed

All prefix commands (!mk\*) have been converted to modern slash commands or removed to streamline the interface.

### Web Dashboard Integration

The bot integrates with a web dashboard for bulk war review:

- **Dashboard API**: FastAPI backend at `mkw-dashboard-api/`
- **Web Frontend**: Next.js app at `mkw-review-web/`
- **Bulk Sessions**: Created via `/bulkscanimage`, reviewed via web URL
- **Authentication**: Discord OAuth for guild access
- **Features**: Edit 70+ wars at once, approve/reject, link players, manage roster

**Data Flow**:

```
Discord Bot → Dashboard Client → Dashboard API → PostgreSQL
                                       ↑
                           Next.js Web App ←┘
```

### OCR Image Processing Workflow

**Automatic Processing** (Primary Method):

1. **Upload PNG** - User uploads image to configured OCR channel
2. **Auto-Detect** - Bot automatically triggers OCR on new images
3. **Process** - PaddleOCR extracts players and scores from Lorenzi/Ice Mario format
4. **Validate** - Check player names against roster, validate scores (12-180)
5. **Confirm** - React with ✅ (save), ❌ (cancel), or click "Save War" button
6. **Save** - Update database with war results and player statistics

**Manual Processing** (Backup):

1. **Command** - Use `/scanimage` if auto-OCR missed an image
2. **Process** - Same OCR processing as automatic
3. **Confirm** - Same confirmation workflow

**Bulk Processing**:

1. **Command** - Use `/bulkscanimage` to scan entire channel
2. **Process** - Scans all images in channel (up to 100)
3. **Review URL** - Bot provides web dashboard link
4. **Web Review** - Edit/approve/reject all wars in browser
5. **Save All** - One-click to save all approved wars

### Database Schema

- **players**: Player roster with guild_id, nicknames (JSONB), team assignments (replaced old 'roster' table)
- **wars**: Race session data with guild_id and player results
- **guild_configs**: Per-guild settings, team names, allowed channels

**Note**: The database has been updated to use the `players` table instead of the old `roster` and `player_stats` tables for better data consistency.

## Development Guidelines

### Before Making Changes

- **Check Existing Patterns**: Review similar implementations in codebase
- **Database Changes**: Always test with `admin/check_database.py`
- **OCR Changes**: Test with sample images in `testing/sample_images/`
- **Command Changes**: Follow existing command structure in `commands.py`

### Adding New Features

- **Discord Commands**: Add to `MarioKartCommands` cog in `commands.py`
- **Database Operations**: Add methods to `DatabaseManager` in `database.py`
- **OCR Processing**: Extend `OCRProcessor` in `ocr_processor.py`
- **Configuration**: Add to `config.py` with environment variable support

### Testing Requirements

- **Unit Tests**: Test database operations and OCR processing
- **Integration Tests**: Test Discord command workflows
- **Manual Testing**: Use sample images and test commands in Discord

## Configuration Management

### Environment Variables

- **Required**: `DISCORD_BOT_TOKEN`
- **Database**: `DATABASE_URL` (Railway auto-configures)
- **Optional**: `GUILD_ID`, `CHANNEL_ID`, `ALLOWED_CHANNELS`
- **Development**: `DATABASE_PUBLIC_URL` for local development

### Player Configuration

- **Roster**: Edit `CLAN_ROSTER` in `config.py`
- **Nicknames**: Use `admin/manage_nicknames.py` for database management
- **Teams**: Support for team assignments and team-based commands

## Common Issues & Solutions

### Database Connection

- **Connection Pooling**: 1-10 connections configured
- **Railway**: Uses `DATABASE_URL` automatically
- **Local**: Set `DATABASE_PUBLIC_URL` for development

### OCR Processing

- **Tesseract**: Auto-detects installation path
- **Image Quality**: Preprocesses images for better OCR results
- **Name Resolution**: Uses nickname system for fuzzy matching

### Discord Integration

- **Intents**: Requires message content and reactions intents
- **Permissions**: Bot needs reaction management permissions
- **Rate Limits**: Handles Discord API rate limiting

## Deployment Notes

### Railway Deployment

- **Database**: PostgreSQL service automatically configured
- **Build**: Uses `requirements.txt` for dependencies
- **Environment**: Set `DISCORD_BOT_TOKEN` in Railway dashboard

### Local Development

- **Virtual Environment**: Use `python -m venv venv`
- **Dependencies**: `pip install -r requirements.txt`
- **Database**: Use Railway PostgreSQL URL for testing

## Known Issues

- **Paginated Menu Reactions**: Reaction buttons remain highlighted after use
- **Workaround**: Users must manually uncheck reactions for repeated actions
- **Status**: UI/UX issue only, functionality works correctly

## Version Management

- **Current**: 0.1.0-alpha (active development)
- **Semantic Versioning**: MAJOR.MINOR.PATCH
  - MAJOR: Breaking changes/incompatible API changes
  - MINOR: New features, backwards compatible
  - PATCH: Bug fixes, backwards compatible
- **Pre-release**: Use -alpha/-beta/-rc suffixes during development

## OCR Optimization System (Railway Environment Variables)

### Overview

The enhanced OCR system provides priority-based resource allocation, dynamic load balancing, and Railway-optimized performance for Mario Kart image processing.

### Key Features

- **Priority-based Processing**: EXPRESS (single images), STANDARD (small bulk), BACKGROUND (large bulk)
- **Dynamic Resource Borrowing**: Higher priority operations can borrow unused resources
- **Adaptive Mode Switching**: Auto-adjusts between bulk_heavy, single_focused, and balanced modes
- **Performance Monitoring**: Real-time metrics collection and optimization recommendations
- **Railway Optimization**: Specifically tuned for Railway's 8GB RAM / 8 vCPU environment

### Railway Environment Variables

#### Core OCR Settings

```bash
OCR_MODE=balanced                      # Options: bulk_heavy, single_focused, balanced
OCR_MAX_CONCURRENT=2                   # Base concurrent operations limit
OCR_ENABLE_PRIORITY_BORROWING=true     # Enable resource borrowing between priority tiers
OCR_ENABLE_USAGE_ADAPTATION=true       # Auto-adapt mode based on usage patterns
```

#### Priority-based Resource Limits

```bash
OCR_EXPRESS_MAX_CONCURRENT=4           # Express priority (single images)
OCR_STANDARD_MAX_CONCURRENT=2          # Standard priority (small bulk scans 2-10 images)
OCR_BACKGROUND_MAX_CONCURRENT=1        # Background priority (large bulk scans 10+ images)
OCR_BORROWING_THRESHOLD=0.8            # 80% utilization threshold for borrowing
```

#### PaddleOCR Performance Settings

```bash
OCR_PADDLE_CPU_THREADS=4               # CPU threads for PaddleOCR processing
OCR_MEMORY_LIMIT_MB=2048               # Memory limit per OCR operation
OCR_BATCH_SIZE=3                       # Batch size for bulk processing operations
```

#### Advanced Optimizations (Optional)

```bash
OCR_ENABLE_ADVANCED_OPTIMIZATIONS=false  # Enable additional Railway optimizations
OCR_ENABLE_PERFORMANCE_LOGGING=true      # Enable performance monitoring
OCR_METRICS_INTERVAL=30                  # Performance metrics collection interval (seconds)
OCR_USAGE_WINDOW_MINUTES=60             # Time window for usage pattern analysis
OCR_BULK_OPERATION_THRESHOLD=10         # Images count to classify as bulk operation
```

#### Railway Environment Limits

```bash
RAILWAY_MAX_CPU_CORES=8                # Railway CPU core limit
RAILWAY_MAX_MEMORY_GB=8                # Railway memory limit
```

### OCR Modes

#### bulk_heavy Mode

- **When**: Heavy bulk scanning periods (e.g., initial setup)
- **Optimization**: Maximizes background processing resources
- **Best for**: Processing 50+ images, historical data imports

#### single_focused Mode

- **When**: Mostly single image processing (e.g., steady state)
- **Optimization**: Prioritizes fast response times for individual images
- **Best for**: Real-time war result processing (~hourly)

#### balanced Mode (Default)

- **When**: Mixed usage patterns
- **Optimization**: Balanced resource allocation across all priority levels
- **Best for**: General purpose usage with varying workloads

### Resource Borrowing Logic

The system implements intelligent resource borrowing:

1. **EXPRESS Operations**: Can borrow from STANDARD and BACKGROUND when needed
2. **STANDARD Operations**: Can borrow from BACKGROUND when EXPRESS isn't using resources
3. **BACKGROUND Operations**: Uses dedicated resources, no borrowing capability

Borrowing is triggered when:

- Target priority tier is at capacity
- Source tier utilization is below threshold (default 80%)
- Higher priority operation is waiting

### Performance Monitoring

When `OCR_ENABLE_PERFORMANCE_LOGGING=true`:

- Real-time resource utilization tracking
- Average wait times and processing times
- Success rates and error tracking
- Automatic mode switching recommendations
- Memory usage and cleanup optimization

### Usage Examples

#### Development/Testing

```bash
OCR_MODE=single_focused
OCR_MAX_CONCURRENT=1
OCR_ENABLE_PERFORMANCE_LOGGING=true
```

#### Launch Period (Heavy Bulk Scanning)

```bash
OCR_MODE=bulk_heavy
OCR_BACKGROUND_MAX_CONCURRENT=3
OCR_BATCH_SIZE=5
OCR_ENABLE_USAGE_ADAPTATION=true
```

#### Steady State Operation

```bash
OCR_MODE=single_focused
OCR_EXPRESS_MAX_CONCURRENT=6
OCR_ENABLE_PRIORITY_BORROWING=true
```

#### Balanced Production

```bash
OCR_MODE=balanced
OCR_ENABLE_PRIORITY_BORROWING=true
OCR_ENABLE_USAGE_ADAPTATION=true
OCR_ENABLE_PERFORMANCE_LOGGING=true
```

### Architecture Components

#### New Files

- `ocr_config_manager.py`: Railway environment variable configuration management
- `ocr_resource_manager.py`: Priority-based semaphore system with resource borrowing
- `ocr_performance_monitor.py`: Real-time performance tracking and adaptive optimization

#### Enhanced Files

- `ocr_processor.py`: Added async processing methods with resource management integration
- `bot.py`: Enhanced bulk scan processing with priority-based resource allocation
- `config.py`: Extended with OCR optimization environment variables

### Backwards Compatibility

All existing functionality is preserved:

- Existing `/bulkscanimage` command works unchanged
- Synchronous OCR processing methods remain functional
- Graceful fallback to basic mode if resource management unavailable
- No breaking changes to database operations or user experience

### Monitoring and Debugging

Use the following to monitor OCR performance:

- Check bot logs for resource utilization messages
- Monitor Railway CPU and memory usage
- Review performance metrics in Discord bot logs
- Adjust environment variables based on usage patterns

### Troubleshooting

#### High Wait Times

- Increase `OCR_MAX_CONCURRENT` or priority-specific limits
- Enable `OCR_ENABLE_PRIORITY_BORROWING=true`
- Consider switching to `bulk_heavy` mode for bulk operations

#### Memory Issues

- Reduce `OCR_MEMORY_LIMIT_MB`
- Decrease `OCR_BATCH_SIZE`
- Lower concurrent operation limits

#### Low Performance

- Enable `OCR_ENABLE_ADVANCED_OPTIMIZATIONS=true`
- Increase `OCR_PADDLE_CPU_THREADS` (max 8 for Railway)
- Monitor performance logs for optimization suggestions
