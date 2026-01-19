# Railway Deployment Guide

## Quick Deployment to Railway

This guide shows how to deploy the Solana Trading Bot to Railway.app.

### Prerequisites

1. [Railway account](https://railway.app) (free tier available)
2. GitHub repository with your bot code
3. Telegram session file generated locally

### Environment Variables

⚠️ **CRITICAL**: Railway requires environment variables to be set BEFORE deployment!

Configure these in Railway's dashboard under **Variables** tab:

#### Required Variables (⚠️ MUST SET)

```bash
# Telegram API Credentials (get from https://my.telegram.org/apps)
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=abcdef1234567890abcdef1234567890
TELEGRAM_SESSION_NAME=wallet_tracker_session

# Trading Configuration
TRADING_ENABLED=true
TRADING_DRY_RUN=true
TRADING_BUY_AMOUNT_SOL=0.1
TRADING_SELL_PERCENTAGE=50
TRADING_MIN_MULTIPLIER=2.0
TRADING_MAX_POSITIONS=10

# Channel Configuration
SIGNAL_CHANNEL=fttrenches_volsm
GMGN_BOT=GMGN_sol_bot

# File Paths (Railway-specific)
STATE_FILE=/app/data/trading_state.json
LOG_FILE=/app/data/trading_bot.log
```

**How to get Telegram API credentials:**
1. Go to https://my.telegram.org/apps
2. Log in with your phone number
3. Click "API development tools"
4. Fill in the application details
5. Copy `api_id` and `api_hash`

### Deployment Steps

#### 1. Push Code to GitHub

```bash
git add .
git commit -m "Prepare for Railway deployment"
git push origin main
```

#### 2. Create Railway Project

1. Go to [Railway Dashboard](https://railway.app/dashboard)
2. Click **"New Project"**
3. Select **"Deploy from GitHub repo"**
4. Choose your repository
5. Railway will auto-detect the Dockerfile

#### 3. Add Environment Variables (⚠️ DO THIS BEFORE DEPLOYING)

1. In Railway dashboard, click on your project
2. Go to **Variables** tab
3. Click **"New Variable"**
4. Add **each variable** from the required list above:
   - Click **"New Variable"**
   - Enter variable name (e.g., `TELEGRAM_API_ID`)
   - Enter value (e.g., `12345678`)
   - Click **"Add"**
5. Repeat for **all required variables**
6. Once all variables are added, click **"Deploy"**

**Common mistake**: Forgetting to add `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` will cause the bot to crash immediately!

#### 4. Upload Telegram Session File

The bot requires a Telegram session file that was generated locally.

**Option A: Use Railway CLI** (Recommended)

```bash
# Install Railway CLI
npm i -g @railway/cli

# Login
railway login

# Link to your project
railway link

# Upload session file
railway run --service=trading-bot bash -c "cat > /app/wallet_tracker_session.session" < wallet_tracker_session.session
```

**Option B: Mount Volume (Not Available on Free Tier)**

Railway's Pro plan supports persistent volumes.

**Option C: Generate Session in Container**

Add these environment variables temporarily:

```bash
TELEGRAM_PHONE=+1234567890
```

Then run:

```bash
railway run python -c "from telethon import TelegramClient; client = TelegramClient('wallet_tracker_session', YOUR_API_ID, 'YOUR_API_HASH'); client.start()"
```

#### 5. Monitor Logs

```bash
# Via CLI
railway logs

# Or in Railway Dashboard
# Go to "Deployments" > Click latest deployment > View logs
```

### Troubleshooting

#### Missing Environment Variables (COMMON)

```
❌ Missing required environment variable: TELEGRAM_API_ID
❌ Missing required environment variable: TELEGRAM_API_HASH
```

**Solution**: Add environment variables in Railway dashboard!

1. Go to your project in Railway
2. Click **"Variables"** tab
3. Add the missing variables:
   ```
   TELEGRAM_API_ID=your_actual_api_id
   TELEGRAM_API_HASH=your_actual_api_hash
   ```
4. Click **"Redeploy"**

**How to get these values:**
- Visit https://my.telegram.org/apps
- Log in and create an app
- Copy the `api_id` and `api_hash` values

#### Permission Denied Error

If you see `PermissionError: [Errno 13] Permission denied: '/app/trading_bot.log'`:

✅ **Fixed in latest version!** The bot now:
- Automatically uses `/app/data/` for logs (writable directory)
- Falls back to console-only logging if no writable location exists
- Respects `LOG_FILE` environment variable

Verify your `LOG_FILE` is set to `/app/data/trading_bot.log` in Railway variables.

#### Session File Not Found

```
FileNotFoundError: wallet_tracker_session.session
```

**Solution**: Generate the session file locally first:

```bash
python -c "
from telethon import TelegramClient
client = TelegramClient('wallet_tracker_session', YOUR_API_ID, 'YOUR_API_HASH')
client.start()
"
```

Then upload using Railway CLI (Option A above).

#### Container Crashes on Start

Check logs for specific error:

```bash
railway logs --tail 100
```

Common issues:
- Missing environment variables (check Variables tab)
- Invalid API credentials
- Session file not uploaded

### Resource Usage

**Free Tier Limits:**
- 500 hours/month
- 512MB RAM
- 1GB storage

**Bot Requirements:**
- ~50-100MB RAM under normal load
- Minimal CPU usage
- ~10MB storage (logs + state)

✅ **The bot fits within Railway's free tier!**

### Health Checks

Railway automatically monitors the container. The bot includes a health check:

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"
```

### Logs Persistence

Logs are stored in `/app/data/trading_bot.log` but **NOT persisted across deployments** on Railway's free tier.

For persistent logs, consider:
- Railway Pro (persistent volumes)
- External logging service (Papertrail, Logtail)
- Database logging

### State Persistence

The bot saves state to `/app/data/trading_state.json`. This file contains:
- Open positions
- Trade history
- Statistics

⚠️ **Important**: State is lost on container restart in Railway free tier.

**Workaround**: Implement state backup to external storage (S3, PostgreSQL, etc.)

### Stopping the Bot

```bash
# Via CLI
railway down

# Or in Railway Dashboard
# Project Settings > "Delete Service"
```

### Costs

| Plan | Price | Features |
|------|-------|----------|
| **Free** | $0/mo | 500 hrs/month, 512MB RAM |
| **Pro** | $5/mo + usage | Persistent volumes, more resources |

**Estimated cost for 24/7 operation:**
- Free tier: $0 (fits within 500 hrs/month limit)
- Pro tier: ~$5-10/mo

### Alternative: Deploy with Docker Compose

If Railway doesn't fit your needs, use Docker Compose locally or on a VPS:

```bash
docker-compose up -d
```

See [DOCKER_GUIDE.md](DOCKER_GUIDE.md) for details.

---

## Support

- Report issues: [GitHub Issues](https://github.com/nhattruong0204/solana-trenches-trading-bot/issues)
- Railway docs: https://docs.railway.app
- Telegram API: https://core.telegram.org/
