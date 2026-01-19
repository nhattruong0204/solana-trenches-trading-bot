# 🐳 Docker Deployment Guide

Complete guide for deploying the Solana Trading Bot using Docker.

---

## Prerequisites

1. **Docker installed**: [Install Docker](https://docs.docker.com/get-docker/)
2. **Docker Compose installed**: Usually comes with Docker Desktop
3. **Telegram session file**: `wallet_tracker_session.session` must exist

---

## Quick Start

### 1. Configure Environment

```bash
cd /home/truong/sol_wallet_tracker/trading_bot

# Create .env file
cp .env.docker .env

# Edit with your credentials
nano .env
```

Add your Telegram API credentials:
```env
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=abcdef1234567890abcdef1234567890
TELEGRAM_PHONE=+1234567890
```

### 2. Ensure Session File Exists

The bot needs an authenticated Telegram session. If you don't have it:

```bash
# Go to parent directory
cd /home/truong/sol_wallet_tracker

# Run any script to create session
python fetch_trenches_volume.py

# Copy session file to trading_bot folder
cp wallet_tracker_session.session trading_bot/
```

### 3. Start the Bot

```bash
cd trading_bot

# Simple start
./docker-run.sh up

# Or manually
docker-compose up -d
```

### 4. Monitor Logs

```bash
# Live logs
./docker-run.sh logs

# Or manually
docker-compose logs -f
```

---

## Docker Commands

### Using the Helper Script

```bash
# Start bot
./docker-run.sh up

# Stop bot
./docker-run.sh down

# Restart bot
./docker-run.sh restart

# View logs
./docker-run.sh logs

# Check status
./docker-run.sh status

# Rebuild image
./docker-run.sh build

# Open shell in container
./docker-run.sh shell

# Clean up everything
./docker-run.sh clean
```

### Manual Docker Compose Commands

```bash
# Build and start
docker-compose up -d

# Stop
docker-compose down

# Restart
docker-compose restart

# View logs
docker-compose logs -f

# Check status
docker-compose ps

# Rebuild image
docker-compose build --no-cache

# Remove volumes
docker-compose down -v
```

---

## File Structure

```
trading_bot/
├── Dockerfile              # Docker image definition
├── docker-compose.yml      # Service configuration
├── .dockerignore          # Files to exclude from build
├── .env                   # Environment variables (create from .env.docker)
├── .env.docker            # Template for .env
├── docker-run.sh          # Helper script for Docker operations
├── trading_bot.py         # Main bot code
├── requirements.txt       # Python dependencies
├── wallet_tracker_session.session  # Telegram session (required!)
├── trading_state.json     # Bot state (created automatically)
└── trading_bot.log        # Log file (created automatically)
```

---

## Volume Mounts

The Docker container mounts these files for persistence:

| Host Path | Container Path | Purpose |
|-----------|---------------|---------|
| `./trading_state.json` | `/app/trading_state.json` | Trading positions |
| `./trading_bot.log` | `/app/trading_bot.log` | Log output |
| `./wallet_tracker_session.session` | `/app/wallet_tracker_session.session` | Telegram auth |

These files persist across container restarts.

---

## Deploy to Cloud Services

### DigitalOcean App Platform

1. Create app from GitHub repo
2. Set environment variables in dashboard
3. Deploy automatically

### AWS ECS/Fargate

```bash
# Tag image
docker tag trading-bot:latest your-ecr-repo/trading-bot:latest

# Push to ECR
docker push your-ecr-repo/trading-bot:latest

# Deploy via ECS console or CLI
```

### Google Cloud Run

```bash
# Build and push
gcloud builds submit --tag gcr.io/your-project/trading-bot

# Deploy
gcloud run deploy trading-bot \
  --image gcr.io/your-project/trading-bot \
  --platform managed \
  --set-env-vars TELEGRAM_API_ID=xxx,TELEGRAM_API_HASH=xxx
```

### Heroku

```bash
# Login to Heroku
heroku login

# Create app
heroku create solana-trading-bot

# Push Docker container
heroku container:push web -a solana-trading-bot
heroku container:release web -a solana-trading-bot

# Set env vars
heroku config:set TELEGRAM_API_ID=xxx -a solana-trading-bot
heroku config:set TELEGRAM_API_HASH=xxx -a solana-trading-bot
```

### Railway.app

1. Connect GitHub repo
2. Railway auto-detects Dockerfile
3. Set environment variables in dashboard
4. Deploy automatically

### Render.com

1. Create new Web Service
2. Connect repo
3. Set Docker build command: `docker build -f trading_bot/Dockerfile .`
4. Add environment variables
5. Deploy

---

## Environment Variables

Required variables in `.env`:

```env
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=your_api_hash_here
TELEGRAM_PHONE=+1234567890
TELEGRAM_SESSION_NAME=wallet_tracker_session
```

Get Telegram credentials from: https://my.telegram.org

---

## Monitoring

### View Container Status

```bash
docker-compose ps
```

Expected output:
```
NAME                  STATUS          PORTS
solana-trading-bot   Up 5 minutes
```

### View Logs

```bash
# Live logs
docker-compose logs -f

# Last 100 lines
docker-compose logs --tail=100

# Logs from specific time
docker-compose logs --since 1h
```

### Check Resource Usage

```bash
# Container stats
docker stats solana-trading-bot

# Disk usage
docker system df
```

### Access Container Shell

```bash
docker-compose exec trading-bot /bin/bash

# Check files
ls -la
cat trading_bot.log
cat trading_state.json
```

---

## Troubleshooting

### Bot won't start

```bash
# Check logs
docker-compose logs

# Common issues:
# 1. Missing .env file
#    Solution: cp .env.docker .env && nano .env

# 2. Missing session file
#    Solution: Copy from parent directory

# 3. Build errors
#    Solution: docker-compose build --no-cache
```

### Session expired

```bash
# Stop container
docker-compose down

# Regenerate session on host
cd /home/truong/sol_wallet_tracker
python fetch_trenches_volume.py

# Copy new session
cp wallet_tracker_session.session trading_bot/

# Restart container
cd trading_bot
docker-compose up -d
```

### Container keeps restarting

```bash
# Check logs
docker-compose logs --tail=50

# Check if session file is valid
docker-compose exec trading-bot ls -la wallet_tracker_session.session

# Restart with fresh build
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Out of disk space

```bash
# Clean up old images
docker system prune -a

# Remove old logs
> trading_bot.log

# Remove unused volumes
docker volume prune
```

---

## Backup & Restore

### Backup Important Files

```bash
# Create backup directory
mkdir -p backups/$(date +%Y%m%d)

# Backup state and logs
cp trading_state.json backups/$(date +%Y%m%d)/
cp trading_bot.log backups/$(date +%Y%m%d)/
cp .env backups/$(date +%Y%m%d)/
```

### Automated Backup (Cron)

```bash
# Add to crontab
crontab -e

# Backup daily at 2 AM
0 2 * * * cd /home/truong/sol_wallet_tracker/trading_bot && \
  mkdir -p backups/$(date +\%Y\%m\%d) && \
  cp trading_state.json backups/$(date +\%Y\%m\%d)/ && \
  find backups -type d -mtime +7 -exec rm -rf {} +
```

---

## Security Best Practices

### 1. Don't Commit Secrets

Never commit `.env` or session files to Git:

```bash
# .gitignore (already configured)
.env
*.session
```

### 2. Use Docker Secrets (Production)

For production deployments, use secrets management:

```yaml
services:
  trading-bot:
    secrets:
      - telegram_api_id
      - telegram_api_hash

secrets:
  telegram_api_id:
    external: true
  telegram_api_hash:
    external: true
```

### 3. Read-Only Session File

Session file is mounted read-only in docker-compose.yml:

```yaml
- ./wallet_tracker_session.session:/app/wallet_tracker_session.session:ro
```

### 4. Limited Permissions

Run container as non-root user (optional):

```dockerfile
# Add to Dockerfile
RUN useradd -m -u 1000 trader
USER trader
```

---

## Performance Optimization

### Reduce Image Size

Already using `python:3.11-slim` (smallest Python image)

### Multi-stage Build (Optional)

For even smaller images:

```dockerfile
FROM python:3.11-slim as builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH
COPY . .
CMD ["python", "-u", "trading_bot.py"]
```

---

## Cost Comparison (Cloud Services)

| Service | Price/Month | Free Tier | Notes |
|---------|-------------|-----------|-------|
| Railway.app | $5+ | $5 credit | Easy deployment |
| Render.com | $7+ | 750 hrs free | Auto-sleep on free tier |
| DigitalOcean | $6+ | $200 credit | Reliable VPS |
| Heroku | $7+ | No free tier | Easy setup |
| AWS Fargate | $10+ | 12 months free | Complex setup |
| Google Cloud Run | Variable | Always free tier | Pay per use |
| Fly.io | $5+ | Limited free | Edge deployment |

---

## Next Steps

1. ✅ Configure `.env` with your Telegram credentials
2. ✅ Ensure session file exists
3. ✅ Run `./docker-run.sh up` to start
4. ✅ Monitor with `./docker-run.sh logs`
5. ✅ Let run 24-48 hours in dry-run mode
6. ✅ Enable live trading when confident
7. ✅ Deploy to cloud service of choice

---

## Quick Reference

```bash
# Start bot
./docker-run.sh up

# View logs
./docker-run.sh logs

# Stop bot
./docker-run.sh down

# Check status
./docker-run.sh status
```

That's it! Your bot is now containerized and ready to deploy anywhere! 🚀
