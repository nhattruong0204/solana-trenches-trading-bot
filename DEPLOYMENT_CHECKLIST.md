# 📋 LightNode Deployment Checklist

Use this checklist to ensure smooth deployment to LightNode VPS.

---

## Pre-Deployment Checklist

### ✅ Local Preparation

- [ ] **Telegram Session File Created**
  - File exists: `wallet_tracker_session.session`
  - Authenticated and working
  - Test command: `ls -lh wallet_tracker_session.session`

- [ ] **Environment File Configured**
  - Copy from template: `cp .env.example .env`
  - All required variables set (see below)
  - No placeholder values remaining
  - Test command: `cat .env | grep -v "PASSWORD\|HASH\|TOKEN" | grep "your_"`

- [ ] **Required Environment Variables**
  ```
  ✓ TELEGRAM_API_ID=________
  ✓ TELEGRAM_API_HASH=________
  ✓ TELEGRAM_PHONE=________
  ✓ BOT_TOKEN=________
  ✓ ADMIN_USER_ID=________
  ✓ NOTIFICATION_CHANNEL=________
  ✓ GMGN_WALLET=________ (optional, can set later)
  ✓ SIGNAL_CHANNEL=fttrenches_volsm
  ✓ GMGN_BOT=GMGN_sol_bot
  ```

- [ ] **Docker Files Ready**
  - [ ] `Dockerfile` exists
  - [ ] `docker-compose.yml` exists
  - [ ] `requirements.txt` exists
  - [ ] Source code in `src/` directory

- [ ] **Test Bot Locally** (Optional but Recommended)
  ```bash
  python main.py
  # Should start without errors
  ```

---

## VPS Setup Checklist

### ✅ LightNode Account

- [ ] **Account Created**
  - Registered at lightnode.com
  - Payment method added
  - Email verified

- [ ] **VPS Provisioned**
  - Plan selected (minimum 1GB RAM recommended)
  - Location chosen (closer = lower latency)
  - Operating System: Ubuntu 22.04 LTS
  - VPS IP noted: `___________________`
  - Root password saved securely

### ✅ VPS Access

- [ ] **SSH Access Working**
  ```bash
  ssh root@YOUR_VPS_IP
  # Should connect without errors
  ```

- [ ] **System Updated**
  ```bash
  apt update && apt upgrade -y
  ```

### ✅ Docker Installation

- [ ] **Docker Installed**
  ```bash
  docker --version
  # Should output: Docker version 24.x.x
  ```

- [ ] **Docker Compose Installed**
  ```bash
  docker-compose --version
  # Should output: docker-compose version 1.29.x or 2.x.x
  ```

- [ ] **Docker Service Running**
  ```bash
  systemctl status docker
  # Should show: active (running)
  ```

---

## Deployment Checklist

### ✅ File Transfer

- [ ] **Deployment Package Created**
  ```bash
  tar -czf trading-bot-deploy.tar.gz \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.venv' \
    --exclude='.pytest_cache' \
    .
  ```

- [ ] **Files Transferred to VPS**
  - [ ] `trading-bot-deploy.tar.gz`
  - [ ] `.env` file
  - [ ] `wallet_tracker_session.session`

- [ ] **Files Extracted on VPS**
  ```bash
  cd /opt/solana-trading-bot
  tar -xzf trading-bot-deploy.tar.gz
  ```

### ✅ Permissions

- [ ] **Correct File Permissions**
  ```bash
  chmod 600 .env
  chmod 600 wallet_tracker_session.session
  chmod 755 data/
  ```

- [ ] **Directory Ownership**
  ```bash
  ls -la
  # Verify files are readable
  ```

### ✅ Docker Deployment

- [ ] **Image Built Successfully**
  ```bash
  docker-compose build
  # No errors during build
  ```

- [ ] **Container Started**
  ```bash
  docker-compose up -d
  # Container state: Up
  ```

- [ ] **Container Running**
  ```bash
  docker-compose ps
  # State should be "Up"
  ```

- [ ] **No Immediate Errors**
  ```bash
  docker-compose logs --tail=50
  # Check for errors
  ```

---

## Verification Checklist

### ✅ Bot Functionality

- [ ] **Telegram Connection**
  ```bash
  docker-compose logs | grep "Connected to Telegram"
  # Should see: ✅ Connected to Telegram
  ```

- [ ] **GMGN Bot Connection**
  ```bash
  docker-compose logs | grep "Connected to GMGN bot"
  # Should see: ✅ Connected to GMGN bot
  ```

- [ ] **Channel Monitoring**
  ```bash
  docker-compose logs | grep "Monitoring channel"
  # Should see: ✅ Monitoring channel: From The Trenches...
  ```

- [ ] **Notification Bot Started**
  ```bash
  docker-compose logs | grep "Notification bot started"
  # Should see: ✅ Notification bot started
  ```

### ✅ Telegram Bot Commands

- [ ] **Bot Responds to /menu**
  - Open Telegram
  - Message your bot
  - Send: `/menu`
  - Should receive menu with buttons

- [ ] **Bot Shows Status**
  - Send: `/status`
  - Should show bot status

- [ ] **Bot Shows Settings**
  - Send: `/settings`
  - Should show current configuration

### ✅ Container Health

- [ ] **Container Healthy**
  ```bash
  docker inspect solana-trading-bot | grep -A 5 Health
  # Status should be "healthy"
  ```

- [ ] **Resource Usage Normal**
  ```bash
  docker stats --no-stream solana-trading-bot
  # Memory < 400MB, CPU < 50%
  ```

- [ ] **No Restart Loops**
  ```bash
  docker-compose ps
  # Check restart count (should be 0-1)
  ```

---

## Security Checklist

### ✅ Firewall Configuration

- [ ] **UFW Installed and Configured**
  ```bash
  ufw status
  # Should show: Status: active
  ```

- [ ] **SSH Port Open**
  ```bash
  ufw status | grep 22
  # Should show: 22/tcp ALLOW
  ```

- [ ] **Unnecessary Ports Closed**
  ```bash
  ufw status numbered
  # Verify only SSH is open
  ```

### ✅ File Security

- [ ] **Sensitive Files Secured**
  ```bash
  ls -la .env wallet_tracker_session.session
  # Permissions should be -rw-------
  ```

- [ ] **Temporary Files Removed**
  ```bash
  rm ~/trading-bot-deploy.tar.gz
  rm ~/env-secret.txt
  ```

### ✅ System Security

- [ ] **Root Password Changed** (if default)
- [ ] **SSH Key Authentication Setup** (recommended)
- [ ] **Fail2ban Installed** (optional but recommended)
  ```bash
  apt install fail2ban -y
  systemctl enable fail2ban
  systemctl start fail2ban
  ```

---

## Monitoring Checklist

### ✅ Logging

- [ ] **Log Rotation Configured**
  - Already in docker-compose.yml
  - Verify: `docker inspect solana-trading-bot | grep -A 10 LogConfig`

- [ ] **Application Logs Accessible**
  ```bash
  docker-compose logs -f
  # Should stream logs
  ```

- [ ] **Log File Exists**
  ```bash
  ls -lh data/trading_bot.log
  # Should exist and be growing
  ```

### ✅ Backup

- [ ] **Backup Script Created**
  ```bash
  ls -lh /opt/backup-bot.sh
  # Should be executable
  ```

- [ ] **Manual Backup Tested**
  ```bash
  /opt/backup-bot.sh
  # Should create backup file
  ```

- [ ] **Automated Backup Scheduled**
  ```bash
  crontab -l | grep backup-bot
  # Should show cron entry
  ```

---

## Post-Deployment Checklist

### ✅ 24-Hour Monitoring

- [ ] **Monitor for 24 hours**
  - Check logs every 6 hours
  - Verify no crashes
  - Confirm signals are received

- [ ] **Check State File**
  ```bash
  cat data/trading_state.json
  # Should show current positions
  ```

- [ ] **Verify Notifications**
  - Receive test signal
  - Check notification in Telegram
  - Verify formatting is correct

### ✅ Performance Tuning

- [ ] **Memory Usage Stable**
  ```bash
  docker stats --no-stream
  # Memory should be stable, not growing
  ```

- [ ] **CPU Usage Normal**
  - Baseline: < 5%
  - During signal processing: < 50%

- [ ] **Disk Space Sufficient**
  ```bash
  df -h
  # Should have > 2GB free
  ```

### ✅ Documentation

- [ ] **VPS Credentials Saved**
  - IP address
  - Root password
  - SSH key (if used)

- [ ] **Bot Configuration Documented**
  - Current settings
  - Wallet address
  - Admin user ID

- [ ] **Emergency Contacts**
  - VPS support: support@lightnode.com
  - Telegram bot: @BotFather

---

## Troubleshooting Quick Reference

### Container Won't Start
```bash
docker-compose logs
# Check for session file or env errors
```

### High Memory Usage
```bash
docker-compose down
# Edit docker-compose.yml, increase memory limit
docker-compose up -d
```

### Can't Connect to Telegram
```bash
# Check network
docker-compose exec trading-bot ping -c 3 api.telegram.org
# Verify API credentials
docker-compose exec trading-bot env | grep TELEGRAM_
```

### Permission Denied
```bash
chmod 600 .env wallet_tracker_session.session
chown -R 1000:1000 data/
```

---

## Success Criteria

Your deployment is successful when:

✅ Container shows "Up" status for > 1 hour
✅ Logs show "Bot is now running" message
✅ Telegram bot responds to `/menu` command
✅ Memory usage < 400MB
✅ No error messages in logs
✅ Able to receive and process signals
✅ Notifications arrive in Telegram

---

## Next Steps After Successful Deployment

1. **Enable Live Trading** (when ready)
   ```bash
   # Edit .env
   nano .env
   # Change: TRADING_DRY_RUN=false
   
   # Restart bot
   docker-compose restart
   ```

2. **Setup Alerts**
   - Configure notification preferences
   - Test emergency stop procedures
   - Setup monitoring dashboard

3. **Regular Maintenance**
   - Check logs weekly
   - Review backups monthly
   - Update bot code as needed

4. **Optimize Settings**
   - Adjust buy amounts based on performance
   - Fine-tune multiplier targets
   - Update max positions if needed

---

**Deployment Date:** _________________

**VPS IP:** _________________

**Bot Username:** @_________________

**Admin ID:** _________________

**Notes:**
```


```

---

✨ **Ready to deploy? Follow the [LIGHTNODE_DEPLOYMENT.md](LIGHTNODE_DEPLOYMENT.md) guide!**
