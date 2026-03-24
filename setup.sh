#!/usr/bin/env bash
# ============================================================
# SNIPER — Quick Setup Script for DigitalOcean / Ubuntu
# Run as root:  bash setup.sh
# ============================================================
set -euo pipefail

APP_DIR="/opt/trading-bot"

echo "=== SNIPER Setup ==="

# 1. System packages
echo "[1/6] Installing system packages…"
apt update -qq && apt install -y -qq python3.12 python3.12-venv python3-pip git > /dev/null

# 2. Project directory
echo "[2/6] Setting up ${APP_DIR}…"
mkdir -p "${APP_DIR}/logs"
cp agent.py daemon.py requirements.txt "${APP_DIR}/"
cp .env.example "${APP_DIR}/.env.example"

if [ ! -f "${APP_DIR}/.env" ]; then
    cp .env.example "${APP_DIR}/.env"
    echo "  → Created .env from template. EDIT IT with your real credentials!"
fi

# 3. Virtual environment
echo "[3/6] Creating Python venv…"
cd "${APP_DIR}"
python3.12 -m venv venv 2>/dev/null || python3 -m venv venv
source venv/bin/activate
pip install -q -r requirements.txt

# 4. systemd service
echo "[4/6] Installing systemd service…"
cp config/trading-bot.service /etc/systemd/system/trading-bot.service 2>/dev/null \
  || cp "${OLDPWD}/config/trading-bot.service" /etc/systemd/system/trading-bot.service
systemctl daemon-reload
systemctl enable trading-bot.service

# 5. Log rotation
echo "[5/6] Setting up log rotation…"
cp config/logrotate.conf /etc/logrotate.d/trading-bot 2>/dev/null \
  || cp "${OLDPWD}/config/logrotate.conf" /etc/logrotate.d/trading-bot

# 6. Done
echo "[6/6] Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Edit ${APP_DIR}/.env with your real API keys"
echo "  2. Test:  cd ${APP_DIR} && source venv/bin/activate && python agent.py pre-market"
echo "  3. Start: sudo systemctl start trading-bot.service"
echo "  4. Logs:  journalctl -u trading-bot.service -f"
echo ""
echo "Schedule (UTC → CET):"
echo "  Pre-market:  12:30 UTC = 1:30 PM CET"
echo "  Intraday:    16:00 UTC = 5:00 PM CET"
echo "  EOD:         20:15 UTC = 9:15 PM CET"
echo "  Weekend:     Saturday 13:00 UTC = 2:00 PM CET"
