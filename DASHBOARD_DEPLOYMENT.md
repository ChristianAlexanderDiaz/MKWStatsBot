# MKW Dashboard Deployment Guide

This guide covers deploying the MKW Stats Dashboard alongside your existing bot on Railway.

## Architecture Overview

```
Railway Project
├── mkw-stats-bot (existing Discord bot)
├── mkw-dashboard-api (FastAPI backend)
├── mkw-review-web (Next.js frontend)
└── PostgreSQL (shared database)
```

All services share the same PostgreSQL database and communicate via Railway's private networking.

## Prerequisites

- Existing mkw-stats-bot deployed on Railway
- Discord bot application credentials (Client ID and Client Secret)
- PostgreSQL database already configured

## Step 1: Database Migration

Run the migration script to create dashboard tables:

```bash
cd mkw_stats_bot
python scripts/utilities/migrate_add_dashboard_tables.py
```

This creates:
- `bulk_scan_sessions` - Tracks bulk scan review sessions
- `bulk_scan_results` - Individual OCR results within sessions
- `user_sessions` - Web authentication sessions

## Step 2: Deploy Dashboard API

### 2.1 Create New Service in Railway

1. In your Railway project, click "New Service"
2. Select "GitHub Repo" and choose your repository
3. Set root directory to `mkw-dashboard-api`

### 2.2 Configure Environment Variables

Add these variables in Railway:

```
PORT=8000
DATABASE_URL=${{Postgres.DATABASE_URL}}
DISCORD_CLIENT_ID=<your-bot-client-id>
DISCORD_CLIENT_SECRET=<your-bot-client-secret>
DISCORD_REDIRECT_URI=https://<your-api-domain>/api/auth/callback
JWT_SECRET=<generate-random-secret>
FRONTEND_URL=https://<your-web-domain>
CORS_ORIGINS=https://<your-web-domain>
API_KEY=<generate-shared-secret>
```

### 2.3 Get Discord OAuth Credentials

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Select your mkwstatsbot application
3. Go to OAuth2 section
4. Copy Client ID and Client Secret
5. Add redirect URI: `https://<your-api-domain>/api/auth/callback`

### 2.4 Generate Domain

In Railway, go to Settings > Networking > Generate Domain for the API service.

## Step 3: Deploy Dashboard Web

### 3.1 Create New Service in Railway

1. Click "New Service" in your Railway project
2. Select "GitHub Repo" and choose your repository
3. Set root directory to `mkw-review-web`

### 3.2 Configure Environment Variables

```
NEXT_PUBLIC_API_URL=https://<your-api-domain>
```

### 3.3 Generate Domain

Generate a domain for the web service in Railway settings.

## Step 4: Configure Bot Integration

### 4.1 Update Bot Environment Variables

Add these to your mkw-stats-bot service:

```
DASHBOARD_ENABLED=true
DASHBOARD_API_URL=http://mkw-dashboard-api.railway.internal:8000
DASHBOARD_API_KEY=<same-api-key-from-step-2>
DASHBOARD_WEB_URL=https://<your-web-domain>
```

Note: Use Railway's internal networking (`railway.internal`) for bot-to-API communication.

### 4.2 Redeploy Bot

Trigger a redeployment of your bot to pick up the new environment variables.

## Testing the Integration

### 1. Test OAuth Login

Visit `https://<your-web-domain>` and click "Login with Discord". You should be redirected to Discord and back to the dashboard.

### 2. Test Bulk Scan

In Discord, run `/bulkscanimage` with 5+ images. The bot should:
1. Process all images via OCR
2. Send a summary embed with a "Open Dashboard" link
3. The link should open the review page

### 3. Review Flow

On the review page:
1. Approve/reject individual wars
2. Edit player names or scores if needed
3. Click "Confirm Approved Wars" to save to database

## Environment Variables Reference

### Bot Service
| Variable | Description | Example |
|----------|-------------|---------|
| DASHBOARD_ENABLED | Enable dashboard integration | `true` |
| DASHBOARD_API_URL | API internal URL | `http://mkw-dashboard-api.railway.internal:8000` |
| DASHBOARD_API_KEY | Shared API key | `<random-string>` |
| DASHBOARD_WEB_URL | Public web URL | `https://mkw-dashboard.railway.app` |

### API Service
| Variable | Description | Example |
|----------|-------------|---------|
| PORT | Server port | `8000` |
| DATABASE_URL | PostgreSQL connection string | `${{Postgres.DATABASE_URL}}` |
| DISCORD_CLIENT_ID | Bot application ID | `123456789` |
| DISCORD_CLIENT_SECRET | OAuth2 client secret | `<from-discord>` |
| DISCORD_REDIRECT_URI | OAuth callback URL | `https://<api-domain>/api/auth/callback` |
| JWT_SECRET | Session encryption key | `<random-string>` |
| FRONTEND_URL | Web app URL | `https://<web-domain>` |
| CORS_ORIGINS | Allowed origins | `https://<web-domain>` |
| API_KEY | Bot authentication key | `<same-as-bot>` |

### Web Service
| Variable | Description | Example |
|----------|-------------|---------|
| NEXT_PUBLIC_API_URL | API public URL | `https://<api-domain>` |

## Troubleshooting

### OAuth Redirect Fails
- Verify DISCORD_REDIRECT_URI matches exactly what's in Discord Developer Portal
- Check CORS_ORIGINS includes your web domain

### Bot Can't Create Sessions
- Verify DASHBOARD_API_KEY matches API_KEY on API service
- Check DASHBOARD_API_URL uses .railway.internal domain

### Review Page Shows "Session Not Found"
- Sessions expire after 24 hours
- Verify the token in URL matches a valid session

### Wars Not Saving
- Check browser console for API errors
- Verify user has proper guild permissions in Discord

## Security Considerations

1. **API Key**: Use a strong random string (32+ characters)
2. **JWT Secret**: Generate a unique secret for production
3. **CORS**: Only allow your specific web domain
4. **OAuth**: Never expose client secret in frontend code

## Rollback

To disable dashboard and revert to Discord-only flow:

1. Set `DASHBOARD_ENABLED=false` in bot environment
2. Redeploy bot
3. (Optional) Delete dashboard services from Railway
