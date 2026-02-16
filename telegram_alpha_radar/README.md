# Telegram Alpha Radar

A production-ready Telegram monitoring system that detects trending token contract addresses across your Telegram chats, groups, and channels.

## Features

- **User Account Listener** — Connects via Telethon (MTProto) to monitor all incoming messages
- **Contract Detection** — Regex-based extraction of Solana (Base58) and EVM (0x) addresses with false-positive filtering
- **PostgreSQL Storage** — Async persistence via asyncpg with deduplication and time-window indexing
- **Trending Detection** — Configurable thresholds for mention count, unique chats, and velocity scoring
- **Alert Notifications** — Formatted alerts sent to Telegram Saved Messages with cooldown protection
- **Dexscreener Integration** — Optional liquidity validation to filter low-liquidity tokens
- **Prometheus Metrics** — Optional metrics endpoint for monitoring
- **Graceful Shutdown** — Signal handling for clean teardown

## Project Structure

```
telegram_alpha_radar/
├── __init__.py       # Package metadata
├── app.py            # Main entry point & orchestrator
├── config.py         # Environment-based configuration
├── listener.py       # Telethon message listener
├── parser.py         # Contract address detection
├── storage.py        # PostgreSQL storage layer
├── trending.py       # Trending detection logic
├── notifier.py       # Alert notification system
├── requirements.txt  # Python dependencies
├── Dockerfile        # Container build
├── .env.example      # Example environment file
└── README.md         # This file
```

## Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Telegram API credentials from [my.telegram.org](https://my.telegram.org/apps)

## Setup

### 1. Clone and install dependencies

```bash
cd telegram_alpha_radar
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your credentials
```

### 3. Set up PostgreSQL

```bash
createdb alpha_radar
# The app auto-creates tables on first run
```

### 4. First-time Telegram login

On first run, Telethon will prompt you for a verification code sent to your Telegram account. Run interactively:

```bash
python -m telegram_alpha_radar.app
```

This creates a `.session` file. Subsequent runs will use the saved session.

## Running

### Local

```bash
# Standard mode
python -m telegram_alpha_radar.app

# Debug mode
python -m telegram_alpha_radar.app --debug
```

### Docker

```bash
# Build
docker build -t alpha-radar -f telegram_alpha_radar/Dockerfile .

# Run (interactive for first login)
docker run -it --env-file telegram_alpha_radar/.env alpha-radar

# Run (detached, after session is saved)
docker run -d \
  --name alpha-radar \
  --env-file telegram_alpha_radar/.env \
  -v ./alpha_radar.session:/app/alpha_radar.session \
  -p 9090:9090 \
  --restart unless-stopped \
  alpha-radar
```

### VPS Deployment

1. SSH into your VPS
2. Install Python 3.11+, PostgreSQL, and pip
3. Clone the repository
4. Install dependencies: `pip install -r telegram_alpha_radar/requirements.txt`
5. Copy and configure `.env`
6. Create the database: `createdb alpha_radar`
7. Run interactively once to authenticate with Telegram
8. Use systemd or Docker for persistent execution:

```ini
# /etc/systemd/system/alpha-radar.service
[Unit]
Description=Telegram Alpha Radar
After=network.target postgresql.service

[Service]
Type=simple
User=deploy
WorkingDirectory=/opt/alpha-radar
EnvironmentFile=/opt/alpha-radar/.env
ExecStart=/opt/alpha-radar/venv/bin/python -m telegram_alpha_radar.app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now alpha-radar
```

## Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `TELEGRAM_API_ID` | (required) | Telegram API ID |
| `TELEGRAM_API_HASH` | (required) | Telegram API hash |
| `TELEGRAM_PHONE` | (required) | Phone number for login |
| `TELEGRAM_SESSION_NAME` | `alpha_radar` | Session file name |
| `DB_HOST` | `localhost` | PostgreSQL host |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_USER` | `postgres` | PostgreSQL user |
| `DB_PASSWORD` | (required) | PostgreSQL password |
| `DB_NAME` | `alpha_radar` | Database name |
| `WINDOW_MINUTES` | `5` | Trending detection window |
| `MIN_MENTIONS` | `3` | Minimum mentions to trend |
| `MIN_UNIQUE_CHATS` | `2` | Minimum distinct chats |
| `ALERT_COOLDOWN_MINUTES` | `15` | Cooldown between repeat alerts |
| `TRENDING_CHECK_INTERVAL` | `30` | Seconds between trending checks |
| `DEXSCREENER_ENABLED` | `false` | Enable liquidity filtering |
| `MIN_LIQUIDITY_USD` | `20000` | Minimum liquidity threshold |
| `METRICS_ENABLED` | `false` | Enable Prometheus metrics |
| `METRICS_PORT` | `9090` | Metrics HTTP port |
| `LOG_LEVEL` | `INFO` | Logging level |
| `DEBUG` | `false` | Debug mode |

## Scoring Formula

```
score = mention_count * unique_chats * (1 + velocity_ratio)
```

Where `velocity_ratio = (current_window_mentions - previous_window_mentions) / previous_window_mentions`. Tokens appearing for the first time get a velocity equal to their mention count.
