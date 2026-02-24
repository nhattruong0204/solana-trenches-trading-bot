# Telegram Alpha Radar v2.0

**Production-ready, multi-chain trending token detection system** that monitors all your Telegram messages in real-time and alerts you when tokens start trending.

## Architecture

```
telegram_alpha_radar/
├── app.py                          # Main orchestrator + CLI
├── config.py                       # Environment-based configuration
├── core/
│   ├── models.py                   # Domain models (TokenMatch, TrendingToken, etc.)
│   ├── types.py                    # Chain enum, type aliases
│   └── utils.py                    # Logging setup, UTC helpers
├── detectors/
│   ├── base_detector.py            # ABC — implement to add new chains
│   ├── solana_detector.py          # Base58, 32-44 chars, false-positive filtering
│   └── evm_detector.py             # 0x + 40 hex, normalized lowercase
├── listener/
│   └── telegram_listener.py        # Telethon MTProto user session
├── storage/
│   ├── base_repository.py          # ABC — swap PostgreSQL for Redis, SQLite, etc.
│   └── postgres_repository.py      # asyncpg with connection pooling
├── trending/
│   └── trending_engine.py          # Scoring, velocity, Dexscreener filter
├── notifier/
│   └── telegram_notifier.py        # Alerts to Saved Messages with cooldown
├── schema.sql                      # Database initialization script
├── requirements.txt                # Python dependencies
├── Dockerfile                      # Production container
└── .env.example                    # Configuration template
```

## Features

- **Multi-chain detection**: Solana + EVM with pluggable detector pattern
- **Telethon user session**: Monitors private chats, groups, and channels
- **PostgreSQL storage**: Deduplication, time-window queries, connection pooling
- **Trending engine**: Configurable thresholds, velocity scoring, per-chain ranking
- **Alert notifications**: Formatted messages to Telegram Saved Messages
- **Dexscreener integration**: Optional liquidity validation
- **Prometheus metrics**: `/metrics` endpoint on port 9090
- **Health check**: `/health` endpoint on port 8080
- **CLI flags**: `--debug`, `--dry-run`
- **Graceful shutdown**: SIGINT/SIGTERM handlers
- **Extensible**: Add new chains in ~50 lines

## Scoring Formula

```
score = mentions × 2 + unique_chats × 3 + velocity × 5
```

Where velocity = `(current_mentions - previous_window_mentions) / previous_window_mentions`.
For first-time appearances, velocity = current mention count.

## Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Telegram API credentials from https://my.telegram.org/apps

## Quick Start (Local)

### 1. Clone and install

```bash
cd telegram_alpha_radar
pip install -r requirements.txt
```

### 2. Set up PostgreSQL

```bash
sudo -u postgres psql -c "CREATE USER radar WITH PASSWORD 'your_password';"
sudo -u postgres psql -c "CREATE DATABASE alpha_radar OWNER radar;"
psql -U radar -d alpha_radar -f schema.sql
```

### 3. Configure environment

```bash
cp .env.example .env
nano .env  # Fill in your Telegram credentials and DB password
```

### 4. First run (creates Telegram session)

```bash
python -m telegram_alpha_radar.app
```

You'll be prompted to enter your Telegram verification code once.
After that, the session file is saved and auto-reused.

### 5. Run with options

```bash
# Debug mode
python -m telegram_alpha_radar.app --debug

# Dry run (log alerts without sending)
python -m telegram_alpha_radar.app --dry-run
```

## VPS Deployment

### 1. Server setup (Ubuntu 22.04+)

```bash
# Update system
apt update && apt upgrade -y

# Install PostgreSQL
apt install -y postgresql postgresql-contrib

# Install Python 3.12
apt install -y python3.12 python3.12-venv python3-pip

# Create app directory
mkdir -p /opt/alpha-radar
cd /opt/alpha-radar
```

### 2. Upload code

```bash
# From your local machine:
scp -r telegram_alpha_radar/ root@YOUR_VPS_IP:/opt/alpha-radar/
```

### 3. Set up virtual environment

```bash
cd /opt/alpha-radar
python3.12 -m venv venv
source venv/bin/activate
pip install -r telegram_alpha_radar/requirements.txt
```

### 4. Set up database

```bash
sudo -u postgres psql -c "CREATE USER radar WITH PASSWORD 'STRONG_PASSWORD_HERE';"
sudo -u postgres psql -c "CREATE DATABASE alpha_radar OWNER radar;"
sudo -u postgres psql -U radar -d alpha_radar -f telegram_alpha_radar/schema.sql
```

### 5. Configure

```bash
cp telegram_alpha_radar/.env.example telegram_alpha_radar/.env
nano telegram_alpha_radar/.env
```

### 6. Create Telegram session (interactive, one-time)

```bash
cd /opt/alpha-radar
source venv/bin/activate
python -m telegram_alpha_radar.app
# Enter verification code when prompted, then Ctrl+C
```

### 7. Create systemd service

```bash
cat > /etc/systemd/system/alpha-radar.service << 'EOF'
[Unit]
Description=Telegram Alpha Radar
After=network.target postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/alpha-radar
Environment=PATH=/opt/alpha-radar/venv/bin
ExecStart=/opt/alpha-radar/venv/bin/python -m telegram_alpha_radar.app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable alpha-radar
systemctl start alpha-radar
```

### 8. Monitor

```bash
# View logs
journalctl -u alpha-radar -f

# Check status
systemctl status alpha-radar

# Health check
curl http://localhost:8080/health
```

## Docker Deployment

### Build and run

```bash
cd telegram_alpha_radar

# Build
docker build -t alpha-radar .

# Run (first time — interactive for Telegram auth)
docker run -it \
  --env-file .env \
  -v $(pwd)/sessions:/app/sessions \
  -p 8080:8080 \
  -p 9090:9090 \
  alpha-radar

# Run (after session created — background)
docker run -d \
  --name alpha-radar \
  --env-file .env \
  --restart unless-stopped \
  -v $(pwd)/sessions:/app/sessions \
  -p 8080:8080 \
  -p 9090:9090 \
  alpha-radar
```

## Adding a New Chain

1. Create `telegram_alpha_radar/detectors/mychain_detector.py`:

```python
from telegram_alpha_radar.detectors.base_detector import BaseDetector
from telegram_alpha_radar.core.models import TokenMatch

class MyChainDetector(BaseDetector):
    @property
    def chain_name(self) -> str:
        return "mychain"

    async def detect(self, message, chat_id, message_id):
        # Your regex / detection logic here
        return matches
```

2. Add the chain to `core/types.py`:
```python
class Chain(str, Enum):
    MYCHAIN = "mychain"
```

3. Register in `app.py`:
```python
self._detectors = [
    SolanaDetector(),
    EvmDetector(),
    MyChainDetector(),  # <-- add here
]
```

## Running Tests

```bash
pip install pytest pytest-asyncio
pytest tests/test_detectors.py -v
```

## Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEGRAM_API_ID` | — | Telegram API ID |
| `TELEGRAM_API_HASH` | — | Telegram API hash |
| `TELEGRAM_PHONE` | — | Phone number with country code |
| `TELEGRAM_SESSION_NAME` | `alpha_radar` | Session file name |
| `DB_HOST` | `localhost` | PostgreSQL host |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_USER` | `radar` | PostgreSQL user |
| `DB_PASSWORD` | — | PostgreSQL password |
| `DB_NAME` | `alpha_radar` | PostgreSQL database |
| `DB_POOL_MIN` | `2` | Min pool connections |
| `DB_POOL_MAX` | `10` | Max pool connections |
| `TRENDING_WINDOW_MINUTES` | `5` | Detection time window |
| `TRENDING_MIN_MENTIONS` | `3` | Min mentions to trend |
| `TRENDING_MIN_UNIQUE_CHATS` | `2` | Min unique chats to trend |
| `TRENDING_COOLDOWN_MINUTES` | `15` | Alert cooldown |
| `TRENDING_CHECK_INTERVAL` | `30` | Seconds between trending checks |
| `FILTER_MIN_MSG_LENGTH` | `5` | Minimum message length |
| `FILTER_IGNORE_FORWARDED` | `false` | Skip forwarded messages |
| `DEXSCREENER_ENABLED` | `false` | Enable liquidity filter |
| `DEXSCREENER_MIN_LIQUIDITY` | `1000` | Min USD liquidity |
| `METRICS_ENABLED` | `false` | Enable Prometheus metrics |
| `METRICS_PORT` | `9090` | Prometheus port |
| `HEALTH_ENABLED` | `true` | Enable health endpoint |
| `HEALTH_PORT` | `8080` | Health check port |
| `LOG_LEVEL` | `INFO` | Logging level |
| `LOG_JSON` | `false` | JSON structured logging |
