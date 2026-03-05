# MKW Stats Bot

> Track your Mario Kart clan's war results, stats, and roster — directly in Discord.

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0+-3178C6?style=flat&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Next.js](https://img.shields.io/badge/Next.js-15-black?style=flat&logo=next.js&logoColor=white)](https://nextjs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=flat&logo=docker&logoColor=white)](https://www.docker.com/)

<!-- [![Add to Server](#)](https://github.com/ChristianAlexanderDiaz/MKWStatsBot) [![Docs](https://img.shields.io/badge/Docs-Command%20Reference-blue)](docs/COMMANDS.md) [![Report Bug](https://img.shields.io/badge/Report-Bug-red)](https://github.com/ChristianAlexanderDiaz/MKWStatsBot/issues) -->

![Screenshot of MKW Stats Bot processing war results](image-2.png)

Upload a screenshot of your war results. The bot reads it, logs the war, and updates every player's stats automatically — no manual entry needed.

It runs entirely inside Discord and supports 50+ members, multiple teams, and hundreds of wars.

## Features

- **Automatic OCR** — Upload a Lorenzi's Game Boards or Ice Mario screenshot to a configured channel; the bot detects players and scores without any commands
- **Smart name matching** — Fuzzy matching and a nickname system handle OCR misreads (e.g. `Wi11ow` → `Willow`) automatically after the first correction
- **Full stats tracking** — Per-player averages, differentials, win/loss records, and leaderboards; filter by last X wars
- **Bulk scan** — Process 50+ historical screenshots at once through a web review dashboard
- **Team management** — Organize players into teams, track member status (Member/Trial/Ally/Kicked), and manage your roster
- **Multi-server support** — Complete data isolation between Discord servers
- **Web dashboard** — Review and edit bulk OCR results in a browser before committing them

## Quick Setup

1. Invite the bot to your server
2. Run `/setup teamname:Your Clan players:Player1,Player2 results_channel:#results`
3. Run `/setchannel channel:#war-results` to set the auto-scan channel
4. Upload a war screenshot — the bot handles the rest

## Commands Overview

| Command            | What it does                                  |
| ------------------ | --------------------------------------------- |
| `/setup`           | First-time server initialization              |
| `/setchannel`      | Set the auto-OCR channel                      |
| `/scanimage`       | Manually scan the latest image                |
| `/bulkscanimage`   | Bulk-scan all images, open web dashboard      |
| `/stats`           | View leaderboard or a specific player's stats |
| `/roster`          | View full team roster                         |
| `/addplayer`       | Add a player to the roster                    |
| `/addnickname`     | Register an OCR nickname for a player         |
| `/addwar`          | Manually log a war result                     |
| `/showallwars`     | Browse war history                            |
| `/assignplayers`   | Assign players to a team                      |
| `/setmemberstatus` | Update a player's status (Member/Trial/etc.)  |

Full command reference with all options and examples: **[docs/COMMANDS.md](docs/COMMANDS.md)**

## How OCR Works

Upload a PNG screenshot from Lorenzi's Game Boards or Ice Mario to the configured channel. The bot reads the image, extracts player names and scores, and presents a confirmation message. Click "Save War" to commit the results — player stats update instantly. If a name is misread, correct it once and register it as a nickname; the bot will recognize it automatically from then on.

## Support

Open an issue on [GitHub](https://github.com/ChristianAlexanderDiaz/MKWStatsBot/issues) for bug reports or feature requests.

## License

MIT License — see [LICENSE](LICENSE) for details.
