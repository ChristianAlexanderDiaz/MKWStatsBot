# Database Management Guide

This guide covers all database management tools for the Mario Kart World Clan Stats Bot.

## 📊 Statistics Calculation System

The bot now uses a **simplified statistics system**:

- **War Count**: 1 war per score entry (each race result = 1 war)
- **Total Scores**: Sum of all scores in the score_history array
- **Average Score**: total_scores ÷ war_count

### Example:

If a player has scores `[100, 90, 110]`:

- **Score History**: `[100, 90, 110]`
- **Total Scores**: `300` (100 + 90 + 110)
- **War Count**: `3` (3 scores = 3 wars)
- **Average Score**: `100.0` (300 ÷ 3)

## 🛠️ Database Management Tools

### 1. Check Database Status

```bash
python tools/check_clan_db.py                    # Show all player stats
python tools/check_clan_db.py player Cynical     # Show specific player
python tools/check_clan_db.py sessions           # Show recent sessions
python tools/check_clan_db.py info               # Show database info
```

### 2. Reset Database (Keep Names & Nicknames)

```bash
python tools/reset_database.py
```

**What it does:**

- ✅ Keeps all player names and nicknames
- ❌ Clears all scores and statistics
- ❌ Removes all race sessions
- ⚠️ Requires confirmation (`yes` to proceed)

**Use case:** Start fresh for testing or new season while keeping roster.

### 3. Manage Player Nicknames

#### Interactive Management:

```bash
python tools/manage_nicknames.py
```

**Options:**

1. Show all players and nicknames
2. Update player nicknames (replace all)
3. Add nickname to player
4. Remove nickname from player
5. Exit

#### Bulk Update (Reset All Nicknames):

```bash
python tools/manage_nicknames.py bulk
```

**What it does:**

- Updates all 24 clan members with their standard nicknames
- Useful after database reset or setup

### 4. Initialize/Setup Players

```bash
python tools/setup_players.py
```

**What it does:**

- Creates all 24 clan members if they don't exist
- Sets up standard nicknames for each player
- Safe to run multiple times (won't duplicate)

## 📋 Common Workflows

### Testing Workflow:

1. **Reset database**: `python tools/reset_database.py`
2. **Verify clean state**: `python tools/check_clan_db.py info`
3. **Test with bot**: Upload images to Discord
4. **Check results**: `python tools/check_clan_db.py`

### Nickname Management Workflow:

1. **View current**: `python tools/manage_nicknames.py` → Option 1
2. **Update specific player**: Option 2 or 3
3. **Verify changes**: Option 1 again

### Season Reset Workflow:

1. **Backup current data** (if needed)
2. **Reset database**: `python tools/reset_database.py`
3. **Verify players preserved**: `python tools/check_clan_db.py info`
4. **Update nicknames if needed**: `python tools/manage_nicknames.py bulk`

## 🗄️ Database Structure

### Players Table:

- `main_name`: Primary player name (e.g., "Cynical")
- `nicknames`: JSON array of alternate names (e.g., ["Cyn", "Christian"])
- `score_history`: JSON array of all scores (e.g., [100, 90, 110])
- `total_scores`: Sum of all scores
- `war_count`: Number of wars (= number of scores)
- `average_score`: total_scores ÷ war_count
- `updated_at`: Last update timestamp

### Race Sessions Table:

- `session_date`: Date of the session
- `race_count`: Number of races in the session
- `players_data`: JSON data of all results
- `created_at`: When session was saved

## 🔍 Troubleshooting

### "Player not found" errors:

- Check exact spelling: `python tools/manage_nicknames.py` → Option 1
- Player names are case-sensitive
- Use main name, not nickname

### Statistics seem wrong:

- Check score history: `python tools/check_clan_db.py player PlayerName`
- Verify calculation: total_scores ÷ war_count should equal average_score

### Database corruption:

1. Check database info: `python tools/check_clan_db.py info`
2. If issues persist, reset and reinitialize:
   ```bash
   python tools/reset_database.py
   python tools/setup_players.py
   ```

## 📊 Current Clan Roster

The bot manages these 24 clan members:

| Main Name  | Nicknames         |
| ---------- | ----------------- |
| Cynical    | Cyn, Christian    |
| rx         | Astral, Astralixv |
| Corbs      | Corby             |
| sopt       | soppy             |
| Dicey      | (none)            |
| Quick      | Q                 |
| DEMISE     | Dems, Dem         |
| Ami        | (none)            |
| Benji      | (none)            |
| Danika     | (none)            |
| Hollow     | (none)            |
| Jacob      | (none)            |
| Jake       | J                 |
| James      | (none)            |
| Juice      | (none)            |
| Klefki     | Klek              |
| Koopalings | Koopa             |
| Minty      | (none)            |
| Moon       | (none)            |
| Mook       | (none)            |
| Nick F     | NickF             |
| Vortex     | (none)            |
| Wilbur     | (none)            |
| yukino     | yuki              |

## 💡 Tips

- **Always backup** important data before major changes
- **Test with small data** before processing large batches
- **Use nickname resolution** - "Cyn" automatically becomes "Cynical"
- **Check database info** regularly to monitor size and player count
- **Reset responsibly** - it clears ALL statistics permanently
