# 🚀 LightNode VPS Deployment Guide

Complete guide for deploying the Solana Trading Bot to LightNode.com Docker VPS.

---

## Overview

This guide walks you through deploying the bot on a LightNode VPS with Docker support.

**What you'll need:**
- LightNode VPS with Docker installed
- SSH access to your VPS
- Telegram session file
- Environment configuration

---

## Step 1: Prepare Your VPS on LightNode

### 1.1 Create VPS Instance

1. Go to [LightNode.com](https://lightnode.com)
2. Select a VPS plan (minimum recommended: 1GB RAM, 1 CPU)
3. Choose location closest to you
4. Select OS: **Ubuntu 22.04 LTS** (recommended)
5. Complete purchase and note your VPS IP address

### 1.2 Access Your VPS

```bash
# SSH into your VPS (replace with your IP)
ssh root@YOUR_VPS_IP
```

### 1.3 Install Docker

```bash
# Update system
apt update && apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Install Docker Compose
apt install docker-compose -y

# Verify installation
docker --version
docker-compose --version

# Enable Docker to start on boot
systemctl enable docker
systemctl start docker
```

---

## Step 2: Prepare Your Bot Files Locally

### 2.1 Create Session File (if not exists)

**On your local machine:**

```bash
cd /home/truong/sol_wallet_tracker/solana-trenches-trading-bot

# If you don't have a session file, create it:
# Run any telegram script once to authenticate
python -c "
from telethon import TelegramClient
import os
from dotenv import load_dotenv
load_dotenv()

api_id = os.getenv('TELEGRAM_API_ID')
api_hash = os.getenv('TELEGRAM_API_HASH')
phone = os.getenv('TELEGRAM_PHONE')

client = TelegramClient('wallet_tracker_session', api_id, api_hash)
client.start(phone)
print('✅ Session created!')
client.disconnect()
"

# Verify session file exists
ls -lh wallet_tracker_session.session
```

### 2.2 Configure Environment File

```bash
# Create production .env file
cp .env.example .env.production

# Edit the file
nano .env.production
```

**Required Configuration:**

```env
# Telegram API (from https://my.telegram.org/apps)
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=your_api_hash_here
TELEGRAM_PHONE=+1234567890
TELEGRAM_SESSION_NAME=wallet_tracker_session

# Telegram Bot (from @BotFather)
BOT_TOKEN=8558125753:AAHu8ggmhWCqsdug016jEy0b-ozo9zI8slU
ADMIN_USER_ID=1846478619
NOTIFICATION_CHANNEL=-1003642289740

# Trading Settings
TRADING_ENABLED=true
TRADING_DRY_RUN=false  # Set to false for live trading
TRADING_BUY_AMOUNT_SOL=0.1
TRADING_SELL_PERCENTAGE=50
TRADING_MIN_MULTIPLIER=2.0
TRADING_MAX_POSITIONS=10

# Channels
SIGNAL_CHANNEL=fttrenches_volsm
GMGN_BOT=GMGN_sol_bot

# GMGN Wallet (your trading wallet)
GMGN_WALLET=YOUR_WALLET_ADDRESS_HERE

# PostgreSQL (if using database features)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_secure_password
POSTGRES_DATABASE=wallet_tracker

# File Paths (for Docker)
STATE_FILE=/app/data/trading_state.json
LOG_FILE=/app/data/trading_bot.log
```

### 2.3 Test Docker Build Locally (Optional)

```bash
# Build the Docker image
docker-compose build

# Test run (will exit if session not mounted properly)
docker-compose up
```

---

## Step 3: Deploy to LightNode VPS

### 3.1 Create Deployment Package

```bash
# On your local machine
cd /home/truong/sol_wallet_tracker/solana-trenches-trading-bot

# Create deployment tarball with all necessary files
tar -czf trading-bot-deploy.tar.gz \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.venv' \
  --exclude='node_modules' \
  --exclude='.pytest_cache' \
  --exclude='trading_state.json' \
  --exclude='.env' \
  . wallet_tracker_session.session

# Create a separate secure file for environment
# (We'll transfer this separately for security)
cp .env.production env-secret.txt
```

### 3.2 Transfer Files to VPS

```bash
# Transfer the deployment package
scp trading-bot-deploy.tar.gz root@YOUR_VPS_IP:/root/

# Transfer session file separately (more secure)
scp wallet_tracker_session.session root@YOUR_VPS_IP:/root/

# Transfer environment file (encrypted channel recommended)
scp env-secret.txt root@YOUR_VPS_IP:/root/
```

### 3.3 Setup on VPS

**SSH into your VPS:**

```bash
ssh root@YOUR_VPS_IP
```

**Extract and setup:**

```bash
# Create app directory
mkdir -p /opt/solana-trading-bot
cd /opt/solana-trading-bot

# Extract deployment package
tar -xzf ~/trading-bot-deploy.tar.gz

# Move environment file
mv ~/env-secret.txt .env

# Verify session file
ls -lh wallet_tracker_session.session

# Create data directory
mkdir -p data

# Set proper permissions
chmod 600 .env
chmod 600 wallet_tracker_session.session
chmod 755 data
```

---

## Step 4: Configure Docker on VPS

### 4.1 Review Docker Compose Configuration

```bash
# Check docker-compose.yml
cat docker-compose.yml
```

### 4.2 Update Docker Compose (if needed)

If you need to adjust resource limits:

```bash
nano docker-compose.yml
```

Adjust these values based on your VPS specs:

```yaml
deploy:
  resources:
    limits:
      cpus: '1.0'      # Adjust based on VPS
      memory: 512M     # Adjust based on VPS
    reservations:
      cpus: '0.25'
      memory: 128M
```

---

## Step 5: Deploy and Start Bot

### 5.1 Build and Start

```bash
# Build the Docker image
docker-compose build

# Start the bot in detached mode
docker-compose up -d

# Verify it's running
docker-compose ps
```

### 5.2 Check Logs

```bash
# View live logs
docker-compose logs -f

# View last 100 lines
docker-compose logs --tail=100

# Check for errors
docker-compose logs | grep ERROR
```

**Expected output:**
```
solana-trading-bot  | 2026-01-21 00:00:00 | INFO | src.bot | Initializing trading bot...
solana-trading-bot  | 2026-01-21 00:00:00 | INFO | src.bot | ✅ Connected to Telegram
solana-trading-bot  | 2026-01-21 00:00:00 | INFO | src.trader | ✅ Connected to GMGN bot
solana-trading-bot  | 2026-01-21 00:00:00 | INFO | src.notification_bot | ✅ Notification bot started
solana-trading-bot  | 2026-01-21 00:00:00 | INFO | src.bot | 🚀 Bot is now running
```

---

## Step 6: Verify Bot is Working

### 6.1 Check Container Status

```bash
# Check running containers
docker ps

# Check container health
docker inspect solana-trading-bot | grep -A 10 Health
```

### 6.2 Test Telegram Bot

1. Open Telegram on your phone
2. Message your bot (e.g., @my_sol_trenches_trading_bot)
3. Send `/menu` command
4. Verify you receive the menu with buttons

### 6.3 Check Trading Status

```bash
# Check if bot is monitoring
docker-compose logs | grep "Monitoring channel"

# Check for any errors
docker-compose logs | grep -i "error\|exception"
```

---

## Step 7: Production Hardening

### 7.1 Enable Firewall

```bash
# Install UFW if not installed
apt install ufw -y

# Allow SSH (IMPORTANT - do this first!)
ufw allow 22/tcp

# Allow Docker ports (only if needed externally)
# Usually not needed for this bot
# ufw allow 2375/tcp

# Enable firewall
ufw enable

# Check status
ufw status
```

### 7.2 Setup Auto-Restart

Docker Compose is already configured with `restart: unless-stopped`, so the bot will:
- Auto-restart if it crashes
- Auto-start when the VPS reboots

### 7.3 Setup Log Rotation

Already configured in docker-compose.yml:
```yaml
logging:
  driver: json-file
  options:
    max-size: "10m"
    max-file: "5"
```

### 7.4 Secure Sensitive Files

```bash
# Remove the deployment files from home
rm ~/trading-bot-deploy.tar.gz
rm ~/env-secret.txt
rm ~/wallet_tracker_session.session

# Also remove from local machine after deployment
```

---

## Step 8: Monitoring and Maintenance

### 8.1 View Real-Time Logs

```bash
# SSH into VPS
ssh root@YOUR_VPS_IP

# Navigate to app directory
cd /opt/solana-trading-bot

# Follow logs
docker-compose logs -f
```

### 8.2 Check Bot Status

```bash
# Container status
docker-compose ps

# Resource usage
docker stats solana-trading-bot

# Disk usage
du -sh data/
df -h
```

### 8.3 View Trading State

```bash
# Check state file
cat data/trading_state.json | python -m json.tool
```

### 8.4 Common Commands

```bash
# Restart bot
docker-compose restart

# Stop bot
docker-compose stop

# Start bot
docker-compose start

# View logs from last hour
docker-compose logs --since 1h

# Execute command inside container
docker-compose exec trading-bot python -c "print('Hello from container')"
```

---

## Step 9: Updating the Bot

### 9.1 Prepare Update Locally

```bash
# On your local machine
cd /home/truong/sol_wallet_tracker/solana-trenches-trading-bot

# Pull latest changes (if using git)
git pull

# Create new deployment package
tar -czf trading-bot-update.tar.gz \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.venv' \
  --exclude='node_modules' \
  --exclude='.pytest_cache' \
  --exclude='trading_state.json' \
  --exclude='wallet_tracker_session.session' \
  --exclude='.env' \
  .
```

### 9.2 Deploy Update to VPS

```bash
# Transfer update package
scp trading-bot-update.tar.gz root@YOUR_VPS_IP:/root/

# SSH into VPS
ssh root@YOUR_VPS_IP

# Navigate to app directory
cd /opt/solana-trading-bot

# Stop the bot
docker-compose down

# Backup current version
cp -r /opt/solana-trading-bot /opt/solana-trading-bot.backup.$(date +%Y%m%d)

# Extract update (preserves .env and session files)
tar -xzf ~/trading-bot-update.tar.gz

# Rebuild and restart
docker-compose build
docker-compose up -d

# Verify
docker-compose logs -f

# Clean up
rm ~/trading-bot-update.tar.gz
```

---

## Step 10: Backup and Recovery

### 10.1 Backup Important Files

```bash
# On VPS - create backup script
cat > /opt/backup-bot.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/root/bot-backups"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

# Backup state and session
tar -czf $BACKUP_DIR/bot-backup-$DATE.tar.gz \
  -C /opt/solana-trading-bot \
  .env \
  wallet_tracker_session.session \
  data/trading_state.json \
  data/trading_bot.log

# Keep only last 7 backups
ls -t $BACKUP_DIR/bot-backup-*.tar.gz | tail -n +8 | xargs -r rm

echo "✅ Backup created: bot-backup-$DATE.tar.gz"
EOF

# Make executable
chmod +x /opt/backup-bot.sh

# Run backup
/opt/backup-bot.sh
```

### 10.2 Setup Automatic Backups

```bash
# Add to crontab - backup daily at 3 AM
crontab -e

# Add this line:
0 3 * * * /opt/backup-bot.sh >> /var/log/bot-backup.log 2>&1
```

### 10.3 Download Backups

```bash
# From your local machine
scp root@YOUR_VPS_IP:/root/bot-backups/bot-backup-*.tar.gz ~/backups/
```

---

## Troubleshooting

### Container Won't Start

```bash
# Check logs for errors
docker-compose logs

# Check if session file exists and has correct permissions
ls -lh wallet_tracker_session.session
chmod 600 wallet_tracker_session.session

# Check .env file
cat .env | grep -v "PASSWORD\|HASH\|TOKEN"

# Verify Docker is running
systemctl status docker
```

### Bot Can't Connect to Telegram

```bash
# Check logs
docker-compose logs | grep "Telegram"

# Verify API credentials
docker-compose exec trading-bot env | grep TELEGRAM_

# Test network connectivity
docker-compose exec trading-bot ping -c 3 api.telegram.org
```

### Out of Memory

```bash
# Check memory usage
free -h
docker stats

# Increase swap (if needed)
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

### Permission Denied Errors

```bash
# Fix permissions
cd /opt/solana-trading-bot
chown -R 1000:1000 data/
chmod 755 data/
chmod 644 data/*
```

### Bot Keeps Restarting

```bash
# Check exit code
docker-compose ps

# View full logs
docker-compose logs --tail=500

# Check for common issues
docker-compose logs | grep -i "error\|exception\|failed\|denied"
```

---

## Performance Optimization

### For Low-Resource VPS (512MB RAM)

Update docker-compose.yml:

```yaml
deploy:
  resources:
    limits:
      cpus: '0.50'
      memory: 256M
    reservations:
      cpus: '0.10'
      memory: 64M
```

### For High-Resource VPS (2GB+ RAM)

```yaml
deploy:
  resources:
    limits:
      cpus: '2.0'
      memory: 1G
    reservations:
      cpus: '0.25'
      memory: 128M
```

---

## Security Best Practices

### ✅ DO:
- Use strong passwords for database
- Keep .env file permissions at 600
- Enable UFW firewall
- Regular backups
- Monitor logs regularly
- Update Docker images periodically
- Use non-root user in containers (already configured)

### ❌ DON'T:
- Expose Docker ports publicly
- Share .env or session files
- Run with `--privileged` flag
- Disable firewall
- Use default passwords
- Commit sensitive data to git

---

## Cost Estimation (LightNode)

**Minimum Setup:**
- VPS: $7.71/month (1GB RAM, 1 CPU)
- Traffic: Usually included
- **Total: ~$8/month**

**Recommended Setup:**
- VPS: $13.71/month (2GB RAM, 2 CPU)
- Better performance and headroom
- **Total: ~$14/month**

---

## Quick Reference

### Essential Commands

```bash
# Start bot
docker-compose up -d

# Stop bot
docker-compose down

# Restart bot
docker-compose restart

# View logs
docker-compose logs -f

# Status
docker-compose ps

# Update bot
docker-compose down && docker-compose build && docker-compose up -d

# Backup
/opt/backup-bot.sh

# Shell access
docker-compose exec trading-bot bash
```

### File Locations

```
/opt/solana-trading-bot/           # Main app directory
├── .env                            # Environment config
├── wallet_tracker_session.session # Telegram session
├── docker-compose.yml              # Docker config
├── data/                           # Persistent data
│   ├── trading_state.json         # Trading state
│   └── trading_bot.log            # Application logs
└── src/                           # Source code
```

### Support Resources

- Docker Docs: https://docs.docker.com
- LightNode Docs: https://www.lightnode.com/support
- Telegram Bot API: https://core.telegram.org/bots/api
- Project GitHub: [your-repo-url]

---

## Next Steps

After successful deployment:

1. **Test in Telegram**: Send `/menu` to your bot
2. **Monitor for 24h**: Watch logs for any issues
3. **Test trading**: Send a test signal (dry run first)
4. **Setup alerts**: Configure notifications
5. **Enable live trading**: Set `TRADING_DRY_RUN=false` when ready

---

**Happy Trading! 🚀**

For support: [Your contact info]
