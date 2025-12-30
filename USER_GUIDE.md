# Mario Kart Stats Bot - User Guide

> **Simple guide for Discord users - Everything you need to know about tracking your clan's stats**

## 🚀 Getting Started

### First Time Setup

When the bot first joins your server, you need to initialize it:

```
/setup teamname:Your Team Name players:Player1,Player2,Player3 results_channel:#race-results
```

**Example:**
```
/setup teamname:Team Alpha players:Cynical,Willow,Ghost results_channel:#results
```

This creates:
- ✅ Your guild configuration
- ✅ Your first team
- ✅ Initial player roster
- ✅ Sets the channel for automatic OCR

### Set the OCR Channel

After setup, you can change which channel automatically scans images:

```
/setchannel channel:#your-channel
```

**What this does:**
- Any PNG image uploaded to this channel will be automatically scanned
- Bot will detect players and scores from Lorenzi's Game Boards or Ice Mario results
- You'll get a confirmation message to approve or reject the results

---

## 📸 Adding Wars (Race Results)

### Method 1: Automatic OCR (Recommended)

1. **Upload a PNG screenshot** to the configured OCR channel
2. **Must be from**: Lorenzi's Game Boards OR Ice Mario
3. **Bot automatically scans** - No command needed!
4. **Review results** - Bot shows detected players and scores
5. **Approve** - Click "Save War" button or ✅ reaction

That's it! Stats are updated automatically.

### Method 2: Manual Scan

If automatic OCR misses an image, use:

```
/scanimage
```

This manually scans the most recent image in the current channel.

### Method 3: Bulk Scan (For Historical Data)

Upload many old race results at once:

```
/bulkscanimage
```

**How it works:**
1. Bot scans ALL images in the channel
2. Processes them and creates a review session
3. You get a web dashboard link
4. Open the link to review/approve all at once
5. Click "Save All" when done

**Pro Tip**: Use a dedicated channel for bulk scanning to avoid scanning random images!

---

## 📊 Viewing Statistics

### `/stats` - The Main Statistics Command

**View leaderboard (all members):**
```
/stats
```

**View specific player:**
```
/stats player:Cynical
```

**View last X wars only:**
```
/stats player:Cynical lastxwars:10
```

**Sort leaderboard by:**
```
/stats sortby:Average Score    # Default
/stats sortby:Win Rate          # By win percentage
/stats sortby:Average Differential  # By team contribution
```

**What stats are shown:**
- ⚔️ **Performance**: Highest, Average, Lowest scores
- 📈 **Differential**: Team contribution (wins vs losses)
- 📅 **Activity**: Wars played, total races, last war date
- 🏆 **Win/Loss Record**: W-L-T and win percentage

---

## 👥 Managing Players

### Add New Player

```
/addplayer player_name:NewPlayer member_status:Member
```

**Member Status Options:**
- `Member` - Full clan member (shows on leaderboard)
- `Trial` - Trial period
- `Ally` - Allied player
- `Kicked` - Removed player

### Remove Player

```
/removeplayer player_name:PlayerName
```

Deactivates the player but keeps their historical stats.

### Add Nickname (Important for OCR!)

```
/addnickname player_name:Willow nickname:Wi11ow
```

**Why use nicknames?**
OCR sometimes misreads names. Adding nicknames helps the bot automatically recognize variations:
- `Wi11ow` → `Willow` (1 read as l)
- `Gh0st` → `Ghost` (0 read as O)
- `Cyn1cal` → `Cynical` (i read as 1)

### View Nicknames

```
/nicknamesfor player_name:Willow
```

Shows all nicknames for a player.

### Remove Nickname

```
/removenickname player_name:Willow nickname:Wi11ow
```

---

## 🏆 Team Management

### View Roster

```
/roster
```

Shows all players organized by teams.

### Create New Team

```
/addteam team_name:Team Bravo
```

### Assign Players to Team

```
/assignplayers players:Cynical,Willow,Ghost team_name:Team Alpha
```

**Note**: Separate multiple players with commas (no spaces after commas).

### Unassign Player

```
/unassignplayerfromteam player_name:Cynical
```

Sets player to "Unassigned" team.

### View All Teams

```
/showallteams
```

Shows all players grouped by member status (Members, Trials, Allies, Kicked).

### View Specific Team

```
/showspecificteamroster team_name:Team Alpha
```

### Rename Team

```
/renameteam old_name:Team Alpha new_name:Alpha Squad
```

### Remove Team

```
/removeteam team_name:Team Bravo
```

**Note**: This unassigns all players from the team, doesn't delete them.

---

## ⚔️ War Management

### View All Wars

```
/showallwars limit:20
```

Shows recent wars with pagination. Default shows 20.

### Add War Manually

```
/addwar player_scores:Cynical:92,Willow:85,Ghost:78 races:12
```

**Format**: `PlayerName:Score,PlayerName:Score`

### Add Players to Existing War

```
/appendplayertowar war_id:123 player_scores:NewPlayer:95
```

This adds/updates players in an existing war.

### Remove War

```
/removewar war_id:123
```

**Important**: This reverts player statistics! Use carefully.

---

## 🎭 Member Status Commands

### Set Member Status

```
/setmemberstatus player_name:Cynical status:Member
```

**Status Options:**
- `Member` - Full member
- `Trial` - Trial period
- `Ally` - Allied player
- `Kicked` - Removed

### View Trial Members

```
/showtrials
```

Shows all players with Trial status.

### View Kicked Members

```
/showkicked
```

Shows all players with Kicked status.

---

## 🔧 Admin & Debug Commands

### Check Bot Permissions

```
/checkpermissions channel:#your-channel
```

Verifies the bot has all required permissions in a channel.

### Debug OCR

```
/debugocr image_url:https://cdn.discordapp.com/...
```

Admin only - Debug OCR results for troubleshooting.

---

## 💡 Pro Tips

### Getting Best OCR Results

1. **Use PNG format** - JPG works but PNG is better
2. **Use Lorenzi's Game Boards or Ice Mario** - These formats are specifically trained
3. **Full screenshot** - Include the entire results table
4. **Clear resolution** - Make sure text is readable
5. **No cropping** - Include the whole board

### Common OCR Fixes

If OCR misreads a name:
1. **First time**: Edit it manually in the review screen
2. **Add nickname**: `/addnickname player_name:CorrectName nickname:WhatOCRRead`
3. **Next time**: Bot will automatically fix it!

### Bulk Scanning Workflow

1. Create a dedicated `#war-results` channel
2. Upload all historical images there
3. Run `/bulkscanimage`
4. Use the web dashboard link to review
5. Approve all at once
6. Done!

### Understanding Statistics

**Average Score**: Points per war, not per race
- If you play 12 races and score 85 points total, that's 85 for that war
- Your average is the mean of all war scores

**War Count**: Supports partial participation!
- Played only 6/12 races? Counts as 0.5 wars
- This makes averages fair for partial participation

**Team Differential**: Your contribution to team wins/losses
- **Positive** = You're helping the team win
- **Negative** = Below "breakeven" (41 points/race)
- Example: 12 races × 41 = 492 breakeven. Score 520? +28 differential!

**Win/Loss Record**:
- **Win**: Team differential > 0
- **Loss**: Team differential < 0
- **Tie**: Exactly 492 points (41 × 12)

---

## ❓ Frequently Asked Questions

### Why isn't automatic OCR working?

Check:
1. Is the channel set? `/setchannel channel:#your-channel`
2. Is it a PNG image? (JPG might be skipped)
3. Is it from Lorenzi or Ice Mario format?
4. Does the bot have permissions? `/checkpermissions channel:#your-channel`

### Can I edit a war after saving?

Yes! Use:
```
/appendplayertowar war_id:123 player_scores:Player:NewScore
```

This updates or adds players to an existing war.

### How do I delete a war?

```
/removewar war_id:123
```

Find the war ID using `/showallwars`

### Can I track multiple teams?

Yes! Create teams and assign players:
```
/addteam team_name:Team Alpha
/addteam team_name:Team Bravo
/assignplayers players:Player1,Player2 team_name:Team Alpha
```

### What if a player changes teams?

Just reassign them:
```
/assignplayers players:PlayerName team_name:New Team
```

Their stats stay with them!

---

## 🌐 Web Dashboard

Access the web dashboard for a better review experience:

**Features:**
- Review 70+ wars at once
- Edit player names and scores
- Link OCR names to roster players
- Add new players to roster
- Approve/reject with one click

**Access:**
1. Run `/bulkscanimage` in Discord
2. Click the provided review link
3. Sign in with Discord
4. Review and approve all results

---

## 🎯 Command Quick Reference

| Command | What It Does |
|---------|--------------|
| `/setup` | First-time guild initialization |
| `/setchannel` | Set auto-OCR channel |
| `/scanimage` | Manually scan recent image |
| `/bulkscanimage` | Scan all channel images |
| `/stats` | View statistics/leaderboard |
| `/roster` | View full team roster |
| `/addplayer` | Add new player |
| `/addnickname` | Add OCR nickname |
| `/addwar` | Manually add war |
| `/showallwars` | View war history |
| `/assignplayers` | Assign to team |
| `/help` | Show bot help |

---

## 🆘 Getting Help

### In Discord

```
/help
```

Shows comprehensive command help.

### Support Channels

- 🐛 **Bug Reports**: Open GitHub issue
- 💡 **Feature Requests**: GitHub issues
- 📖 **Documentation**: This guide + `/help`

---

<div align="center">

**Happy Racing! 🏁**

[Technical Documentation](README.md) • [Development Guide](mkw_stats_bot/README.md)

</div>
