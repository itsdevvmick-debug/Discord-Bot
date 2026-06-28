# Avenue Assets Discord Bot

A Discord bot for Avenue Assets with moderation, tickets, partnership workflows, giveaways, product posts, announcements, logging, and Render keep-alive support.

## Features

- Moderation: `/kick`, `/ban`, `/unban`, `/mute`, `/unmute`, `/purge`, `/addrole`, `/removerole`, `/warn`, `/slowmode`
- Tickets: `/panel`, ticket dropdowns, support/marketing/management channels, transcript export, close/delete controls
- Marketing partnerships: requirement flow, proof review, partner posting, partner logs
- Giveaways: timed giveaways with role filters and automatic ending after restarts
- Marketing periods: `/startperiod`, `/updateperiod`, `/endperiod`
- Utilities: `/poll`, `/dice`, `/8ball`, `/flip`, `/addproduct`, `/announcement`, `/userinfo`, `/avatar`, `/ping`, `/help`
- Events/logging: welcome, goodbye, message edit/delete, role/channel/member updates

## Local Setup

```powershell
cd C:\Users\Gebruiker\Downloads\67
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python main.py
```

Fill in `.env` before starting the bot:

```env
DISCORD_TOKEN=your_bot_token
SERVER_ID=your_server_id
MODERATOR_ROLE_ID=...
CEO_ROLE_ID=...
```

Leave optional IDs blank until you need that feature. The bot now safely treats blank or placeholder IDs as `0`.

## Discord Developer Portal

Enable these intents:

- Server Members Intent
- Message Content Intent
- Guilds and moderation permissions required by your commands

Recommended bot permissions:

- Manage Channels
- Manage Roles
- Manage Messages
- Kick Members
- Ban Members
- Moderate Members
- Send Messages
- Embed Links
- Use Slash Commands
- Read Message History

The bot role must be higher than roles/members it manages.

## Render Setup

Create a Render Web Service.

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
python main.py
```

Add your `.env` values in Render's Environment section. Render provides `PORT` automatically; the included Flask keep-alive server binds to that port.

SQLite works on Render, but normal deploy storage can be temporary. For persistent logs and giveaway state, add a Render persistent disk and set:

```env
DATABASE_PATH=/var/data/bot_database.db
```

Use the actual mount path from your Render disk settings.

## Important Environment Variables

- `BRAND_NAME=Avenue Assets`
- `BRAND_SHORT_NAME=Avenue`
- `DISCORD_TOKEN`
- `SERVER_ID`
- `MODERATOR_ROLE_ID`
- `MARKETING_ROLE_ID`
- `CEO_ROLE_ID`
- `COO_ROLE_ID`
- `TEAM_LEADER_ROLE_ID`
- `SUPPORT_CATEGORY_ID`
- `MARKETING_CATEGORY_ID`
- `MANAGEMENT_CATEGORY_ID`
- `PARTNERS_CHANNEL_ID`
- `LOGS_CHANNEL_ID`
- `TICKET_LOGS_CHANNEL_ID`
- `PRODUCTS_FORUM_CHANNEL_ID`
- `DATABASE_PATH`

## Notes

- `/panel` requires the CEO role.
- Marketing ticket users type `accept` or `decline` after reading the requirements.
- Product posting supports both text channels and forum channels.
- Giveaway endings are checked every minute, so they can end up to one minute after the exact scheduled time.

© 2026 Avenue Assets. All rights reserved.
