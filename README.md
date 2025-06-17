# MKWStatsBot 🏁

A Discord bot that automatically extracts Mario Kart race results from uploaded images using OCR technology and maintains player statistics in a database.

## Features

- 🖼️ **Automatic Image Processing**: Upload race result images and the bot extracts player names and scores
- 🔍 **OCR Technology**: Uses Tesseract OCR with image preprocessing for accurate text extraction
- 👥 **Team Management**: Supports multiple team rosters with alphabetical organization
- ✅ **Validation System**: Ensures exactly 6 players per team with duplicate detection
- 📊 **Statistics Tracking**: Maintains player averages, total scores, and race counts
- 🏆 **Leaderboards**: View team leaderboards with average scores
- 💾 **Flexible Database**: SQLite for local development, PostgreSQL for cloud deployment
- 🎯 **Table Presets**: Save region selections for consistent OCR on specific table formats

## Quick Start

### 1. Setup Discord Bot

```bash
python utils/setup_discord.py
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Install Tesseract OCR

**macOS:** `brew install tesseract`
**Ubuntu:** `sudo apt-get install tesseract-ocr`

### 4. Run the Bot

```bash
python main.py
# or
./run.sh
```

## Project Structure

```
MKWStatsBot/
├── src/                    # Core bot modules
│   ├── bot.py             # Main Discord bot
│   ├── database.py        # Database operations
│   ├── ocr_processor.py   # OCR and image processing
│   └── config.py          # Configuration
├── utils/                 # Utility scripts
│   ├── setup_discord.py   # Discord bot setup
│   ├── setup_preset.py    # Table format presets
│   ├── test_ocr.py        # OCR testing
│   └── region_selector.py # Interactive region selection
├── docs/                  # Documentation
│   ├── QUICKSTART.md      # Quick start guide
│   └── SETUP_GUIDE.md     # Detailed setup
├── sample_images/         # Sample images and presets
├── main.py               # Main entry point
├── requirements.txt      # Dependencies
└── README.md            # This file
```

## Usage

### Automatic Processing

1. Upload Mario Kart race results image to Discord
2. Bot validates exactly 6 players per team
3. Confirmation message shows extracted results
4. React ✅ to save or ❌ to cancel
5. Statistics automatically updated

### Commands

- `!mkstats` - Show team leaderboard
- `!mkstats [player]` - Show specific player stats
- `!mkteamroster first` - Show team roster
- `!mkpreset list` - Show table format presets
- `!mkhelp` - Show all commands

### Team Configuration

Edit `src/config.py` to customize your team roster:

```python
FIRST_TEAM_ROSTER = [
    "Astralixv", "Christian", "DEMISE", "Dicey",
    "Gravy on Moon", "Klefki", "Minty", "myst.0000",
    "Quick", "sopt", "yukino"
]
```

## Data Engineering Features

This project demonstrates key Data Engineering concepts:

- **ETL Pipeline**: Extract (OCR from images) → Transform (validate/clean) → Load (database)
- **Data Quality**: Input validation, duplicate detection, score range checks
- **Database Design**: Proper schema with foreign keys and calculated fields
- **Analytics**: Player statistics, leaderboards, historical tracking
- **Unstructured Data**: Converting images to structured database records
- **Cloud Deployment**: Environment-based configuration for production

## Cloud Deployment

For 24/7 operation, deploy to:

### Railway.app (Recommended)

1. Connect GitHub repository
2. Add PostgreSQL database
3. Set environment variables
4. Automatic deployments

### Environment Variables

```bash
DISCORD_BOT_TOKEN=your_bot_token
DATABASE_URL=postgresql://... # For cloud deployment
GUILD_ID=123456789            # Optional: restrict to server
CHANNEL_ID=987654321          # Optional: restrict to channel
```

## Development

### Setup Table Presets

```bash
python utils/setup_preset.py sample_image.png
```

### Test OCR

```bash
python utils/test_ocr.py sample_image.png
```

### Local Database

Data stored in `mario_kart_results.db` (SQLite)

## Contributing

1. Fork the repository
2. Create feature branch
3. Make changes
4. Test with sample images
5. Submit pull request

## License

MIT License - see LICENSE file for details

---

**Perfect for Data Engineering portfolios!**
Showcases ETL pipelines, data validation, cloud deployment, and production-ready code.
