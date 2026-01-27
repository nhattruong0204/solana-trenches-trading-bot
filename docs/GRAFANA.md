# Grafana Dashboard Guide

This guide explains how to use the Grafana dashboard for trading bot analytics.

## Prerequisites

Before starting Grafana, ensure:

1. **PostgreSQL is running** with data bootstrapped:
   ```bash
   docker compose up -d postgres
   docker compose ps postgres  # Should be "healthy"
   ```

2. **Bootstrap completed** - Run `/bootstrap` in the trading bot to populate historical data

3. **Required environment variables** in `.env`:
   ```bash
   POSTGRES_PASSWORD=your_secure_password      # Required
   GRAFANA_ADMIN_PASSWORD=your_admin_password  # Required (no default)
   ```

---

## Quick Start

### 1. Start Grafana

```bash
# Start Grafana service
docker compose up -d grafana

# Check it's running
docker compose ps grafana
```

### 2. Access Dashboard

- **URL**: `http://your-server:3000`
- **Username**: `admin`
- **Password**: Set via `GRAFANA_ADMIN_PASSWORD` in `.env` (default: `admin`)

### 3. First-Time Setup

The dashboard is auto-provisioned. Navigate to:
- **Dashboards** > **Trading Bot Dashboards** > **Solana Trading Bot Analytics**

---

## Dashboard Sections

### Row 1: Health Check (30-Second Assessment)

| Panel | Purpose | Good | Warning | Bad |
|-------|---------|------|---------|-----|
| Signal PNL % | Overall profitability | > 10% | 0-10% | < 0% |
| Win Rate % | Signal success rate | > 50% | 30-50% | < 30% |
| Signals Today | Activity check | > 0 | - | 0 |
| Last Signal Age | Bot health | < 60 min | 60-240 min | > 240 min |

### Row 2: Key Performance Indicators

- **Total Signals**: Count of signals in selected period
- **Avg Multiplier**: Average profit multiplier for winning signals
- **Est. Rugged %**: Signals with no profit alerts (likely rugged)
- **Best Multiplier**: Highest multiplier achieved
- **Profit Alerts**: Count of profit alert messages

### Row 3: PNL Analysis

- **Cumulative PNL Over Time**: Fee-adjusted cumulative performance
- **Multiplier Distribution**: Histogram of achieved multipliers

### Row 4: Signal Activity

- **Signals Per Day by Channel**: VOLSM vs MAIN daily signal count
- **7-Day Rolling Win Rate**: Trend of win rate over time

### Row 5: Performance Tables

- **Top 10 Winners**: Best performing signals
- **Worst 10 Losers**: Signals with no profit alerts

### Row 6: Channel Comparison

- **Channel Performance**: Side-by-side VOLSM vs MAIN stats

---

## Dashboard Filters

### Time Range

Select from dropdown:
- `1d` - Last 24 hours
- `7d` - Last 7 days (default)
- `30d` - Last 30 days
- `90d` - Last 90 days
- `365d` - Last year

### Channel Filter

- `All Channels` - Combined view
- `VOLSM` - Volume + Smart Money channel only
- `MAIN` - Main channel only

---

## Understanding the Metrics

### Signal PNL vs Real PNL

| Metric | Source | Description |
|--------|--------|-------------|
| **Signal PNL** | Profit alerts in Telegram | What the channel claims |
| **Real PNL** | DexScreener live prices | Actual market value |

> **Note**: This dashboard shows Signal PNL. For Real PNL, use the `/realpnl` bot command.

### Fee Calculation

The dashboard applies GMGN fee adjustments:
- **Buy Fee**: 2.5%
- **Sell Fee**: 2.5%
- **Breakeven**: ~1.053X

Formula:
```
Net PNL % = (multiplier × 0.95 - 1) × 100
```

### Win/Loss Determination

- **Win**: Signal has at least one profit alert
- **Loss**: No profit alert after 3+ days (assumed rugged)

### Signal Detection Patterns

The dashboard identifies signals using these SQL patterns:

| Channel | Pattern | Example |
|---------|---------|----------|
| VOLSM | `%APE SIGNAL DETECTED%` | `// VOLUME + SM APE SIGNAL DETECTED` |
| MAIN | `%NEW-LAUNCH%` | `🚀 **NEW-LAUNCH SIGNAL**` |
| MAIN | `%MID-SIZED%` | `// MID-SIZED SIGNAL DETECTED` |
| Both | `%PROFIT ALERT%` | `🎯 PROFIT ALERT` |

Profit alerts are linked to signals via `raw_json->>'reply_to_msg_id'`.

---

## Troubleshooting

### Dashboard Not Loading

```bash
# Check Grafana logs
docker compose logs grafana

# Verify PostgreSQL connection
docker exec trading-grafana wget -qO- http://localhost:3000/api/health
```

### No Data Showing

1. Verify signals exist in database:
```bash
docker exec solana-trading-postgres psql -U postgres -d wallet_tracker \
  -c "SELECT COUNT(*) FROM raw_telegram_messages WHERE raw_text LIKE '%SIGNAL%';"
```

2. Check time range filter matches your data
3. Run `/bootstrap` in bot to populate historical data

### Slow Queries

Add performance indexes:
```bash
docker exec solana-trading-postgres psql -U postgres -d wallet_tracker -c "
  CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_rtm_chat_title_timestamp
    ON raw_telegram_messages(chat_title, message_timestamp DESC);
  CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_rtm_raw_json_reply
    ON raw_telegram_messages((raw_json->>'reply_to_msg_id'));
"
```

---

## Security

### Change Default Password

```bash
# In .env file
GRAFANA_ADMIN_PASSWORD=your_secure_password

# Restart Grafana
docker compose up -d grafana
```

### Restrict Access

Grafana is exposed on port 3000. For production:
1. Use a reverse proxy (nginx/traefik) with SSL
2. Or restrict access via firewall rules

Example nginx config:
```nginx
server {
    listen 443 ssl;
    server_name grafana.yourdomain.com;

    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
    }
}
```

---

## Customization

### Adding New Panels

1. Click **Add** > **Visualization**
2. Select PostgreSQL datasource
3. Write SQL query using existing patterns
4. Save dashboard

### Exporting Dashboard

1. Go to Dashboard Settings (gear icon)
2. Click **JSON Model**
3. Copy JSON for backup

---

## Support

- Bot commands: `/signalpnl`, `/realpnl`, `/menu`
- Issues: [GitHub Issues](https://github.com/nhattruong0204/solana-trenches-trading-bot/issues)
