# Mario Kart World Clan Stats Bot

A professional Discord bot for automatically processing Mario Kart race results using OCR and tracking comprehensive clan statistics.

## 🚀 Features

- **Automatic OCR Processing**: Upload race result images and get automatic player detection
- **Clan Member Recognition**: Intelligent nickname resolution (e.g., "Cyn" → "Cynical")
- **War-Based Statistics**: Track averages per war (12 races = 1 war), supporting partial wars
- **Score History**: Complete tracking of individual race scores for each player
- **Manual Editing**: Edit OCR results before saving with intuitive commands
- **Real-time Stats**: View player rankings, recent sessions, and detailed statistics

## 📁 Project Structure

```
mkw_stats_bot/
├── main.py                 # Application entry point
├── requirements.txt        # Python dependencies
├── README.md              # This file
├── LICENSE                # Project license
├── .gitignore            # Git ignore rules
│
├── core/                  # Core application logic
│   ├── bot.py            # Discord bot implementation
│   ├── ocr_processor.py  # OCR and image processing
│   └── __init__.py
│
├── database/             # Database system
│   ├── database.py       # Database manager (v2 system)
│   ├── mario_kart_clan.db # SQLite database file
│   └── __init__.py
│
├── config/               # Configuration files
│   ├── config.py         # Main configuration
│   ├── env_example.txt   # Environment variables example
│   ├── formats/          # OCR table format presets
│   └── __init__.py
│
├── tools/                # Management and utility tools
│   ├── setup_players.py  # Initialize clan players and nicknames
│   ├── check_clan_db.py  # Database inspection tool
│   ├── region_selector.py # OCR region setup tool
│   ├── setup_preset.py   # Table format setup tool
│   └── __init__.py
│
└── docs/                 # Documentation
    ├── QUICKSTART.md     # Quick setup guide
    └── DATABASE_V2_MIGRATION.md # Migration notes
```

## 🛠️ Installation

1. **Clone the repository**

   ```bash
   git clone <repository-url>
   cd mkw_stats_bot
   ```

2. **Create virtual environment**

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**

   ```bash
   # Option 1: Use .env file
   cp config/env_example.txt .env
   # Edit .env with your Discord bot token

   # Option 2: Use environment variables (if already set in .zshrc)
   # No additional setup needed if DISCORD_BOT_TOKEN is already exported
   ```

5. **Initialize clan database**
   ```bash
   python tools/setup_players.py
   ```

## 🎮 Usage

### Starting the Bot

```bash
python main.py
```

### Discord Commands

**Statistics Commands:**

- `!mkstats` - View all player rankings
- `!mkstats PlayerName` - View specific player details
- `!mkrecent` - View recent race sessions
- `!mkdbinfo` - View database information

**Manual Editing Commands:**

- `!mkadd PlayerName 85` - Add player with score
- `!mkupdate PlayerName 92` - Update player's score
- `!mkremove PlayerName` - Remove player
- `!mkshow` - Show current edit session
- `!mksave` - Save edited results

**Utility Commands:**

- `!mkhelp` - Show help message
- `!roster` - Show clan roster

### Database Management Tools

**Check Database:**

```bash
python tools/check_clan_db.py                    # Show all stats
python tools/check_clan_db.py player Cynical     # Show specific player
python tools/check_clan_db.py sessions           # Show recent sessions
python tools/check_clan_db.py info               # Show database info
```

**Manage Players:**

```bash
python tools/setup_players.py                    # Initialize/update clan roster
python tools/manage_nicknames.py                 # Interactive nickname management
python tools/manage_nicknames.py bulk            # Bulk update all nicknames
python tools/reset_database.py                   # Reset stats (keep names/nicknames)
```

## 📊 Database Structure

The bot uses a sophisticated SQLite database with simplified war-based statistics:

### Players Table

- **main_name**: Primary player name (e.g., "Cynical")
- **nicknames**: JSON array of alternate names (e.g., ["Cyn", "Christian"])
- **score_history**: JSON array of all race scores (e.g., [95, 88, 102])
- **total_scores**: Sum of all scores
- **war_count**: Number of wars (1 war per score entry)
- **average_score**: Points per war (total_scores ÷ war_count)

### Race Sessions Table

- **session_date**: Date of the race session
- **race_count**: Number of races in the session
- **players_data**: JSON data of all results

## 🔧 Configuration

### Environment Variables

Create a `.env` file with:

```
DISCORD_BOT_TOKEN=your_bot_token_here
GUILD_ID=your_server_id (optional)
CHANNEL_ID=your_channel_id (optional)
```

### Player Nicknames

Edit `tools/setup_players.py` to add/modify player nicknames:

```python
clan_players = {
    "Cynical": ["Cyn", "Christian"],
    "rx": ["Astral", "Astralixv"],
    # ... more players
}
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For issues or questions:

1. Check the documentation in `docs/`
2. Use the database tools to verify your setup
3. Check the bot logs for error messages
4. Create an issue on GitHub

## 🏁 Quick Start

1. Install dependencies: `pip install -r requirements.txt`
2. Set up environment: Either create `.env` file OR use existing environment variables
3. Initialize database: `python tools/setup_players.py`
4. Start the bot: `./run.sh` (recommended) or `python main.py`
5. Upload a race result image to Discord and watch the magic happen! ✨

**Super Quick Start:** If you already have your Discord token in `.zshrc`, just run `./run.sh`!
