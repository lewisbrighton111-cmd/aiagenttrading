# SNIPER 🎯

**Self-hosted Networked Intelligence Pipeline for Execution Research**

AI-powered multi-asset trading intelligence delivered to Telegram on a schedule.

## Asset Coverage

| Class | Instruments |
|-------|------------|
| **Forex** | EUR/USD, GBP/USD, USD/JPY, AUD/USD, USD/CHF, USD/CAD |
| **Crypto** | BTC/USD, ETH/USD, SOL/USD, XRP/USD |
| **Indices** | S&P 500, Nasdaq 100, Dow Jones, DAX 40, FTSE 100, Nikkei 225 |
| **Commodities** | Crude Oil (WTI), Natural Gas, Wheat, Corn |
| **Metals** | Gold (XAU/USD), Silver (XAG/USD), Platinum, Copper |

## Briefing Schedule

| Briefing | UTC | CET | ET | Model |
|----------|-----|-----|----|-------|
| Pre-market | 12:30 | 1:30 PM | 8:30 AM | sonar-pro |
| Intraday | 16:00 | 5:00 PM | 12:00 PM | sonar |
| EOD Review | 20:15 | 9:15 PM | 4:15 PM | sonar-pro |
| Weekend Deep Dive | Sat 13:00 | Sat 2:00 PM | Sat 9:00 AM | sonar-reasoning-pro |

## Quick Start

### 1. Clone to your server
```bash
ssh root@your-server-ip
git clone https://github.com/lewisbrighton111-cmd/aiagenttrading.git /opt/trading-bot
cd /opt/trading-bot
```

### 2. Run setup
```bash
bash setup.sh
```

### 3. Add your credentials
```bash
nano /opt/trading-bot/.env
```
Fill in:
- `PERPLEXITY_API_KEY` — from [perplexity.ai/settings](https://perplexity.ai/settings)
- `TELEGRAM_BOT_TOKEN` — from @BotFather
- `TELEGRAM_CHAT_ID` — from the getUpdates endpoint

### 4. Test
```bash
cd /opt/trading-bot
source venv/bin/activate
python agent.py pre-market
```

### 5. Start the daemon
```bash
sudo systemctl start trading-bot.service
sudo systemctl status trading-bot.service
```

## Manual Commands

```bash
cd /opt/trading-bot && source venv/bin/activate

python agent.py pre-market    # Full pre-market briefing
python agent.py intraday      # Quick mid-session update
python agent.py eod           # End-of-day review
python agent.py weekend       # Weekly deep dive
```

## Monitoring

Health endpoint runs on port 8080:
```
curl http://your-server-ip:8080/health
```

View logs:
```bash
journalctl -u trading-bot.service -f     # Live daemon logs
tail -f /opt/trading-bot/logs/agent.log   # Agent logs
```

## Customization

Edit instruments in `agent.py` — look for the `FOREX`, `CRYPTO`, `INDICES`, `COMMODITIES`, and `METALS` lists near the top of the file.

Edit schedule times in `daemon.py` — all times are UTC.

Edit models in `.env` — choose between `sonar` (fast/cheap), `sonar-pro` (balanced), and `sonar-reasoning-pro` (deep analysis).

## Estimated Costs

| Item | Monthly Cost |
|------|-------------|
| Perplexity API | ~$1.50–$3.00 |
| DigitalOcean Droplet | $6.00 |
| **Total** | **~$7.50–$9.00** |

## File Structure

```
/opt/trading-bot/
├── agent.py              # Core intelligence pipeline
├── daemon.py             # Scheduler + health endpoint
├── .env                  # Your credentials (not in git)
├── .env.example          # Template
├── requirements.txt      # Python dependencies
├── setup.sh              # One-command setup
├── config/
│   ├── trading-bot.service   # systemd unit file
│   └── logrotate.conf        # Log rotation config
└── logs/
    ├── agent.log
    └── daemon.log
```
