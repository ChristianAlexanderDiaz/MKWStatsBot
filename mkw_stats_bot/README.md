# 🏁 MKW Stats Bot

> **Professional Discord bot for Mario Kart clan statistics with OCR image processing**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![PostgreSQL](https://img.shields.io/badge/database-PostgreSQL-blue.svg)](https://www.postgresql.org/)
[![Railway](https://img.shields.io/badge/deploy-Railway-purple.svg)](https://railway.app/)
[![Discord.py](https://img.shields.io/badge/discord-py-blue.svg)](https://discordpy.readthedocs.io/)

## 🚀 Overview

MKW Stats Bot is a production-ready Discord bot that automatically processes Mario Kart race result images using OCR technology and maintains comprehensive clan statistics. Built with modern Python practices and deployed on Railway with PostgreSQL.

### ✨ Key Features

- 🖼️ **Intelligent OCR Processing** - Upload race images, get automatic player detection
- 🎯 **Smart Name Resolution** - Handles nicknames (e.g., "Cyn" → "Cynical")  
- 📊 **War-Based Statistics** - Tracks averages per war with flexible race counts
- 📈 **Complete Score History** - Detailed tracking of all individual scores
- ✏️ **Manual Editing** - Interactive correction of OCR results
- 🏆 **Real-time Leaderboards** - Live player rankings and statistics
- 🔄 **Confirmation System** - React-based result verification before saving
- 🌐 **Cloud-Native** - Railway deployment with PostgreSQL database

## 📋 Table of Contents

- [Quick Start](#-quick-start)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Usage](#-usage)
- [Deployment](#-deployment)
- [Development](#-development)
- [API Reference](#-api-reference)

## ⚡ Quick Start

### Local Development

```bash
# 1. Clone and setup
git clone <your-repo-url>
cd mkw_stats_bot
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env with your DISCORD_BOT_TOKEN

# 4. Initialize database
python management/setup_players.py

# 5. Start the bot
python main.py
```

### Railway Deployment

```bash
# 1. Create Railway project with PostgreSQL
# 2. Connect your GitHub repository
# 3. Set environment variables:
#    - DISCORD_BOT_TOKEN=your_token
# 4. Deploy automatically runs with Railway
```

## 🛠️ Installation

### Prerequisites

- Python 3.11+
- PostgreSQL (local development) or Railway account
- Discord Bot Token
- Tesseract OCR (for image processing)

### System Dependencies

```bash
# macOS
brew install tesseract

# Ubuntu/Debian
sudo apt-get install tesseract-ocr

# Windows
# Download from: https://github.com/UB-Mannheim/tesseract/wiki
```

### Python Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## ⚙️ Configuration

### Environment Variables

Create `.env` file:

```env
# Required
DISCORD_BOT_TOKEN=your_discord_bot_token

# Optional - Database (auto-configured on Railway)
DATABASE_URL=postgresql://user:pass@host:port/db
RAILWAY_POSTGRES_URL=postgresql://user:pass@host:port/db

# Optional - Discord restrictions
GUILD_ID=your_server_id
CHANNEL_ID=your_channel_id

# Optional - PostgreSQL (local development)
POSTGRES_HOST=localhost
POSTGRES_DB=mkw_stats_dev
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_password
POSTGRES_PORT=5432
```

### Player Configuration

Initialize your clan roster:

```bash
python management/setup_players.py
```

Edit the script to customize your clan members and nicknames.

## 🎮 Usage

### Discord Commands

#### Statistics Commands
- `!mkstats` - View complete player leaderboard
- `!mkstats <player>` - View specific player statistics
- `!mkrecent` - View recent race sessions
- `!mkdbinfo` - View database information and health

#### Manual Editing Commands
- `!mkadd <player> <score>` - Add player with score
- `!mkupdate <player> <score>` - Update player's score
- `!mkremove <player>` - Remove player from session
- `!mkshow` - Show current editing session
- `!mksave` - Save edited results to database

#### Utility Commands
- `!mkhelp` - Show comprehensive help
- `!roster` - Display clan roster

### Image Processing Workflow

1. **Upload Image** - Post race result image to Discord
2. **OCR Processing** - Bot automatically detects players and scores
3. **Confirmation** - React with ✅ to save, ❌ to cancel, ✏️ to edit
4. **Manual Editing** - Use editing commands if needed
5. **Save Results** - Confirmed results update player statistics

### Management Tools

```bash
# Database management
python management/check_database.py          # View all statistics
python management/check_database.py player <name>  # Specific player
python management/reset_database.py         # Reset statistics

# Player management
python management/setup_players.py          # Initialize/update roster
python management/manage_nicknames.py       # Interactive nickname management
```

## 🚀 Deployment

### Railway (Recommended)

1. **Create Railway Project**
   - Go to [railway.app](https://railway.app)
   - Create new project
   - Add PostgreSQL service

2. **Deploy Bot**
   - Connect GitHub repository
   - Set environment variables
   - Deploy automatically

3. **Configure Environment**
   ```env
   DISCORD_BOT_TOKEN=your_token
   # DATABASE_URL auto-configured by Railway
   ```

Detailed guide: [RAILWAY_SETUP.md](RAILWAY_SETUP.md)

### Local Development with Remote Database

```bash
# Use Railway PostgreSQL locally
export DATABASE_URL="postgresql://user:pass@host:port/db"
python main.py
```

## 🔧 Development

### Project Structure

```
mkw_stats_bot/
├── main.py                 # Application entry point
├── requirements.txt        # Dependencies
├── render.yaml            # Railway deployment config
├── mkw_stats/             # Main application package
│   ├── __init__.py
│   ├── bot.py             # Discord bot implementation
│   ├── commands.py        # Discord commands
│   ├── config.py          # Configuration management
│   ├── database.py        # PostgreSQL database layer
│   └── ocr_processor.py   # OCR and image processing
├── management/            # Management tools
│   ├── setup_players.py   # Player initialization
│   ├── check_database.py  # Database inspection
│   ├── manage_nicknames.py # Nickname management
│   └── reset_database.py  # Database reset
├── testing/               # Test utilities
│   ├── test_database.py   # Database tests
│   └── test_ocr.py        # OCR tests
└── data/                  # Data files
    └── formats/           # OCR format configurations
```

### Code Quality

The project follows professional Python standards:

- ✅ Type hints throughout
- ✅ Comprehensive error handling
- ✅ Structured logging
- ✅ Connection pooling
- ✅ Async/await patterns
- ✅ Production-ready deployment

### Testing

```bash
# Run database tests
python testing/test_database.py

# Run OCR tests
python testing/test_ocr.py

# Test database connection
python -m mkw_stats.database
```

## 📊 Database Schema

### Players Table

```sql
CREATE TABLE players (
    id SERIAL PRIMARY KEY,
    main_name VARCHAR(100) UNIQUE NOT NULL,
    nicknames JSONB DEFAULT '[]'::jsonb,
    score_history JSONB DEFAULT '[]'::jsonb,
    total_scores INTEGER DEFAULT 0,
    war_count DECIMAL(10,2) DEFAULT 0.0,
    average_score DECIMAL(10,2) DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### Race Sessions Table

```sql
CREATE TABLE race_sessions (
    id SERIAL PRIMARY KEY,
    session_date DATE NOT NULL,
    race_count INTEGER NOT NULL,
    players_data JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

## 🔍 Troubleshooting

### Common Issues

1. **OCR Not Working**
   ```bash
   # Check Tesseract installation
   tesseract --version
   
   # Install if missing
   brew install tesseract  # macOS
   ```

2. **Database Connection Failed**
   ```bash
   # Test connection
   python -m mkw_stats.database
   
   # Check environment variables
   echo $DATABASE_URL
   ```

3. **Bot Not Responding**
   ```bash
   # Check logs
   tail -f mario_kart_bot.log
   
   # Verify token
   echo $DISCORD_BOT_TOKEN
   ```

### Performance Optimization

- Connection pooling enabled (1-10 connections)
- JSONB indexes for fast nickname lookups
- Automatic timestamp updates
- Efficient OCR processing

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

### Development Setup

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Run linting
flake8 mkw_stats/
black mkw_stats/

# Run type checking
mypy mkw_stats/
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

- 📖 **Documentation** - Check the `/docs` folder
- 🐛 **Issues** - Open GitHub issue
- 💬 **Discussions** - GitHub discussions
- 📧 **Email** - For private inquiries

## 🙏 Acknowledgments

- [discord.py](https://discordpy.readthedocs.io/) - Discord API wrapper
- [psycopg2](https://www.psycopg.org/) - PostgreSQL adapter
- [Railway](https://railway.app/) - Deployment platform
- [Tesseract](https://github.com/tesseract-ocr/tesseract) - OCR engine

---

<div align="center">

**Made with ❤️ for the Mario Kart community**

[⭐ Star this repo](https://github.com/your-username/mkw_stats_bot) • [🐛 Report Bug](https://github.com/your-username/mkw_stats_bot/issues) • [✨ Request Feature](https://github.com/your-username/mkw_stats_bot/issues)

</div>