# MKW Stats Bot — Command Reference

## Getting Started

### `/setup`

First-time initialization for a new server.

```text
/setup teamname:Your Team Name players:@User1 @User2 @User3 results_channel:#race-results role_member:@Member role_trial:@Trial role_ally:@Ally
```

Creates your guild configuration, first team, initial player roster, and sets the auto-OCR channel.

**Parameters:**
- `teamname` — Name for the first team
- `players` — Space-separated Discord @mentions for initial players
- `results_channel` — Channel where auto-OCR will run
- `role_member` — Discord role for full members
- `role_trial` — Discord role for trial members
- `role_ally` — Discord role for ally members

**Example:**
```text
/setup teamname:Team Alpha players:@Cynical @Willow @Ghost results_channel:#results role_member:@Member role_trial:@Trial role_ally:@Ally
```

### `/setchannel`

Change which channel automatically scans uploaded images for war results.

```text
/setchannel channel:#your-channel
```

Any PNG uploaded to this channel will be automatically scanned. Bot will show detected players and scores for approval.

---

## Scanning War Results (OCR)

### Automatic OCR

1. Upload a PNG screenshot to the configured OCR channel
2. Must be from Lorenzi's Game Boards or Ice Mario
3. Bot automatically scans — no command needed
4. Review the detected players and scores
5. Click "Save War" to confirm

### `/scanimage`

Manually trigger a scan on the most recent image in the current channel.

```text
/scanimage
```

Use this if the automatic scan was missed.

### `/bulkscanimage`

Scan all images in the current channel and open a bulk review session.

```text
/bulkscanimage
```

**Workflow:**
1. Bot scans all images in the channel
2. A web dashboard link is provided
3. Open the link, review and edit results
4. Click "Save All" when done

**Tip:** Use a dedicated channel (e.g. `#war-results`) to avoid scanning unrelated images.

---

## Viewing Statistics

### `/stats`

The main statistics command.

**View leaderboard:**
```text
/stats
```

**View a specific player:**
```text
/stats player:Cynical
```

**Limit to last X wars:**
```text
/stats player:Cynical lastxwars:10
```

**Sort leaderboard:**
```text
/stats sortby:Average Score
/stats sortby:Win Rate
/stats sortby:Average Differential
```

### Understanding Your Stats

**Average Score** — Points per war (not per race). If you play 12 races and score 85, that war counts as 85. Your average is the mean across all wars.

**War Count** — Supports partial participation. Playing 6/12 races counts as 0.5 wars, keeping averages fair.

**Team Differential** — Your contribution to team wins/losses relative to the 41 pts/race breakeven.
- Positive = you're helping the team win
- Negative = below breakeven
- Example: 12 races × 41 = 492 breakeven. Score 520 = +28 differential

**W/L Record** — Win if team differential > 0, Loss if < 0, Tie if exactly 492 points.

---

## Player Management

### `/addplayer`

```text
/addplayer user:@Username ingame_name:Willow country:US
```

- `user` — Discord @mention (required)
- `ingame_name` — In-game name for OCR matching (optional, defaults to Discord display name)
- `country` — 2-letter country code for flag display, e.g. `US`, `GB`, `JP` (optional)

### `/removeplayer`

```text
/removeplayer player_name:PlayerName
```

Deactivates the player but keeps their historical stats.

### `/addnickname`

```text
/addnickname player_name:Willow nickname:Wi11ow
```

Teaches the bot to recognize OCR misreads. Common examples:
- `Wi11ow` → `Willow` (1 misread as l)
- `Gh0st` → `Ghost` (0 misread as O)
- `Cyn1cal` → `Cynical` (i misread as 1)

### `/removenickname`

```text
/removenickname player_name:Willow nickname:Wi11ow
```

### `/nicknamesfor`

```text
/nicknamesfor player_name:Willow
```

Shows all nicknames registered for a player.

### `/roster`

```text
/roster
```

Shows all players organized by teams.

### `/listunlinked`

```text
/listunlinked
```

Lists players on the roster who haven't been linked to a Discord account yet.

---

## Team Management

### `/addteam`

```text
/addteam team_name:Team Bravo
```

### `/removeteam`

```text
/removeteam team_name:Team Bravo
```

Unassigns all players from the team but does not delete them.

### `/renameteam`

```text
/renameteam old_name:Team Alpha new_name:Alpha Squad
```

### `/assignplayers`

```text
/assignplayers players:Cynical,Willow,Ghost team_name:Team Alpha
```

Separate multiple players with commas (no spaces after commas).

### `/unassignplayer`

```text
/unassignplayer player_name:Cynical
```

Sets the player to the "Unassigned" team.

### `/showmemberstatus`

```text
/showmemberstatus
```

Shows all active players grouped by member status (Members, Trials, Allies). Kicked players are not shown.

### `/showspecificteamroster`

```text
/showspecificteamroster team_name:Team Alpha
```

---

## War Management

### `/addwar`

Manually add a war without OCR.

```text
/addwar player_scores:Cynical:92,Willow:85,Ghost:78 races:12
```

Format: `PlayerName:Score,PlayerName:Score`

### `/removewar`

```text
/removewar war_id:123
```

Reverts player statistics. Find the war ID with `/showallwars`. Use carefully.

### `/appendplayertowar`

```text
/appendplayertowar war_id:123 player_scores:NewPlayer:95
```

Adds or updates players in an existing war.

### `/showallwars`

```text
/showallwars limit:20
```

Shows recent wars with pagination. Default limit is 20.

---

## Member Status

### `/setmemberstatus`

```text
/setmemberstatus player_name:Cynical status:Member
```

**Status options:** `Member`, `Trial`, `Ally`, `Kicked`

### `/showtrials`

```text
/showtrials
```

Shows all players with Trial status.

### `/showkicked`

```text
/showkicked
```

Shows all players with Kicked status.

---

## Admin / Debug

### `/checkpermissions`

```text
/checkpermissions channel:#your-channel
```

Verifies the bot has all required permissions in a channel.

### `/debugocr`

```text
/debugocr image_url:https://cdn.discordapp.com/...
```

Admin only. Debug OCR output for troubleshooting a specific image.

---

## Pro Tips

### Getting Best OCR Results

1. Use PNG format (JPG works but PNG is better)
2. Use Lorenzi's Game Boards or Ice Mario — these formats are specifically supported
3. Include the full screenshot — don't crop the results table
4. Make sure text is at a readable resolution

### Common OCR Fixes

If OCR misreads a name:
1. **First time:** Edit it manually in the review screen
2. **Add a nickname:** `/addnickname player_name:CorrectName nickname:WhatOCRRead`
3. **Next time:** Bot will fix it automatically

### Bulk Scanning Workflow

1. Create a dedicated `#war-results` channel
2. Upload all historical images there
3. Run `/bulkscanimage`
4. Open the web dashboard link
5. Review and approve all at once

---

## FAQ

**Why isn't automatic OCR working?**
- Is the channel configured? Run `/setchannel channel:#your-channel`
- Is it a PNG? (JPG may be skipped)
- Is it from Lorenzi or Ice Mario format?
- Does the bot have permissions? Run `/checkpermissions channel:#your-channel`

**Can I edit a war after saving?**
Yes. Use `/appendplayertowar war_id:123 player_scores:Player:NewScore` to update or add players.

**How do I find a war's ID?**
Run `/showallwars` — the ID is shown next to each entry.

**Can I track multiple teams?**
Yes. Create teams with `/addteam` and assign players with `/assignplayers`.

**What if a player changes teams?**
Just reassign them with `/assignplayers players:PlayerName team_name:New Team`. Their stats stay with them.

**What does "partial war" mean?**
If a player played fewer races than the full war (e.g. 6/12), the bot counts it proportionally (0.5 wars). This keeps averages accurate.
