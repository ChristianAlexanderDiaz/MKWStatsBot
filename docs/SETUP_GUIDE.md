# Quick Setup Guide 🚀

## For Your Discord Server Setup

### 1. Get Your Bot Token

1. Go to https://discord.com/developers/applications
2. Click "New Application" and give it a name (e.g., "Mario Kart Results Bot")
3. Go to "Bot" tab in the left sidebar
4. Click "Reset Token" and copy the token
5. Save this token securely - you'll need it to run the bot

### 2. Invite Bot to Your Server

Replace `YOUR_CLIENT_ID` with your bot's Client ID (found in "General Information"):

```
https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=274877967360&scope=bot
```

The bot needs these permissions:

- Read Messages
- Send Messages
- Manage Messages
- Embed Links
- Attach Files
- Add Reactions
- Read Message History

### 3. Set Environment Variable

**macOS/Linux:**

```bash
export DISCORD_BOT_TOKEN="your_token_here"
```

**Windows:**

```cmd
set DISCORD_BOT_TOKEN=your_token_here
```

### 4. Run the Bot

```bash
python bot.py
```

## How to Use the Bot

### Upload Race Results

1. Take a screenshot of your Mario Kart 6v6 results
2. Upload the image to your Discord channel
3. The bot will automatically:
   - Extract player names and scores
   - Validate that exactly 6 players are found
   - Ask for confirmation
4. React ✅ to save or ❌ to cancel

### Commands

- `!mkstats` - Show leaderboard
- `!mkstats PlayerName` - Show specific player stats
- `!mkteamroster first` - Show your first team roster
- `!mkhelp` - Show all commands

## Data Storage Location

Your data is saved in:

- **Database**: `mario_kart_results.db` (SQLite file)
- **Presets**: `table_presets.json` (table format settings)
- **Logs**: `mario_kart_bot.log` (error logs)

These files persist between bot restarts, so your data is never lost!

## Setting Up Table Presets (Optional but Recommended)

For better OCR accuracy with consistent table layouts:

1. Take a clear sample image of your typical 6v6 results
2. Run: `python setup_preset.py sample_image.png`
3. Select regions around each team's player list
4. Save the preset - the bot will use this for future images

## Team Roster Configuration

Edit `config.py` to add your team members:

```python
FIRST_TEAM_ROSTER = [
    "Astralixv",
    "Christian",
    "DEMISE",
    "Dicey",
    "Gravy on Moon",
    "Klefki",
    "Minty",
    "myst.0000",
    "Quick",
    "sopt",
    "yukino"
]
```

The bot will only extract and save results for players on your roster.

## Troubleshooting

**Bot not responding?**

- Check the bot token is set correctly
- Verify bot has proper permissions in your server
- Check `mario_kart_bot.log` for error messages

**OCR not accurate?**

- Ensure images are clear and high resolution
- Set up a table preset for your specific format
- Check that player names match your roster exactly

**Database issues?**

- The database file is created automatically
- Check file permissions if you get write errors
- Database persists between restarts automatically
