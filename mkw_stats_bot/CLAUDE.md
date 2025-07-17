# MKW Stats Bot - Claude Development Guide

## Project Overview
- **Purpose**: Discord bot for Mario Kart clan statistics with OCR image processing
- **Architecture**: Python Discord bot + PostgreSQL database + Tesseract OCR
- **Version**: 0.1.0-alpha (in active development/testing)
- **Deployment**: Railway with PostgreSQL, Docker support
- **Multi-Guild Support**: Full data isolation between Discord servers

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
- **roster**: Players are scoped to their guild_id
- **wars**: War sessions are isolated per guild_id
- **player_stats**: Statistics are calculated per guild_id
- **guild_configs**: Per-guild settings and configurations

### Guild Management Commands
- **Setup**: `!mkguildsetup [guild_name]` - Initialize guild configuration
- **Configure**: `!mkguildconfig [action] [value]` - Manage guild settings
- **Information**: `!mkguildinfo` - View guild statistics and configuration
- **Team Names**: Configure custom team names per guild
- **Channel Restrictions**: Limit bot usage to specific channels

### Migration Process
1. **Run Migration**: `python scripts/utilities/migrate_add_guild_support.py`
2. **Existing Data**: Automatically migrated to default guild_id (0)
3. **Test Setup**: `python testing/test_multi_guild.py`
4. **Guild Setup**: Use `!mkguildsetup` in each Discord server

### Guild Configuration Options
- **Guild Name**: Display name for the guild
- **Team Names**: Custom team names (default: Phantom Orbit, Moonlight Bootel)
- **Allowed Channels**: Restrict bot commands to specific channels
- **Active Status**: Enable/disable guild functionality

### Data Isolation
- **Complete Separation**: No data leakage between guilds
- **Independent Operations**: All commands scoped to current guild
- **Secure Architecture**: Guild ID extracted from Discord context
- **Database Constraints**: Foreign keys enforce guild-level isolation

## Discord Bot Architecture

### Command Structure (45+ commands total)
- **Prefix**: All commands use `!mk` prefix
- **Statistics**: `!mkstats [player]`, `!mkrecent`
- **Roster Management**: `!mkroster`, `!mkadd`, `!mkremove`
- **Team Management**: `!mkassignteam`, `!mkteams`, `!mkteamroster`
- **Nickname Management**: `!mkaddnickname`, `!mkaddnicknames`, `!mkremovenickname`
- **War Management**: `/addwar`, `!mkremovewar`, `!mklistwarhistory`
- **Edit Mode**: `!mkeditadd`, `!mkupdate`, `!mksave`
- **Utility**: `!mkhelp`, `!mkpreset`

### OCR Image Processing Workflow
1. **Upload**: User uploads race result image to Discord
2. **Process**: Bot automatically detects and processes with OCR
3. **Validate**: Check player names against roster, validate scores (12-180)
4. **Confirm**: React with ✅ (save), ❌ (cancel), ✏️ (edit)
5. **Save**: Update database with war results and player statistics

### Database Schema
- **roster**: Player roster with guild_id, nicknames (JSONB), team assignments
- **wars**: Race session data with guild_id and player results
- **player_stats**: Calculated statistics (averages, war counts) per guild
- **guild_configs**: Per-guild settings, team names, allowed channels

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