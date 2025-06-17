# Quick Start Guide ⚡

Get your Mario Kart Discord bot running in 5 minutes!

## 🚀 Discord Bot Setup

### Step 1: Create Discord Bot

1. Go to https://discord.com/developers/applications
2. Click "New Application" → Name it "Mario Kart Results Bot"
3. Go to "Bot" tab → Click "Add Bot"
4. **Important**: Enable "Message Content Intent" under Privileged Gateway Intents

### Step 2: Get Your Secrets

1. In "Bot" tab: Click "Reset Token" → Copy the token
2. In "General Information" tab: Copy the "Application ID" (this is your Client ID)

### Step 3: Easy Setup Script

```bash
python setup_discord.py
```

This will:

- Create a `.env` file with your bot token
- Generate the invite URL for your bot
- Set up security (.gitignore)

### Step 4: Invite Bot to Server

Use the invite URL from the setup script, or manually create one:

```
https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=274877967360&scope=bot
```

### Step 5: Install & Run

```bash
pip install -r requirements.txt
python bot.py
```

## 🧪 Test It Out

1. Upload a Mario Kart results screenshot to your Discord channel
2. The bot will automatically process it and ask for confirmation
3. React ✅ to save or ❌ to cancel

## 🔧 Commands to Try

- `!mkhelp` - Show all commands
- `!mkstats` - Show leaderboard
- `!mkteamroster first` - Show your team roster

## ⚙️ What You Can Ignore in Discord Portal

**Safe to ignore:**

- Public Key
- Interactions Endpoint URL
- Linked Roles
- Verification
- Terms of Service
- Installation settings
- Emojis
- Most OAuth2 settings (except URL Generator)

**Only need:**

- Bot Token (keep secret!)
- Client/Application ID (safe to share)
- Message Content Intent (enable this!)

## 🔒 Security Notes

- ✅ Bot token is in `.env` file (not committed to Git)
- ✅ `.gitignore` prevents secrets from being uploaded
- ✅ Use environment variables for all secrets

## 🆘 Troubleshooting

**Bot not responding?**

- Check bot token is correct in `.env`
- Make sure "Message Content Intent" is enabled
- Verify bot has permissions in your server

**OCR not working?**

- Install tesseract: `brew install tesseract` (macOS)
- Make sure images are clear and readable

**Permission errors?**

- Make sure bot has "Send Messages" and "Add Reactions" permissions
- Check the invite URL includes the right permissions

## 📊 Data Storage

- SQLite database saves all results locally
- Data persists when bot restarts
- Files are in your project directory

Ready to test? Upload a Mario Kart results image! 🏁
