#!/usr/bin/env python3
"""
SNIPER Daemon — Schedule-based runner for trading briefings.
All times are UTC.

Enhanced schedule (UTC → CET):
  06:00 UTC =  7:00 AM CET  — Early morning scan (pre-Asia close)
  08:00 UTC =  9:00 AM CET  — European open briefing
  10:00 UTC = 11:00 AM CET  — Mid-morning update
  12:30 UTC =  1:30 PM CET  — Pre-US session briefing
  14:30 UTC =  3:30 PM CET  — US open update
  16:00 UTC =  5:00 PM CET  — Afternoon check
  18:00 UTC =  7:00 PM CET  — Late session update
  20:15 UTC =  9:15 PM CET  — EOD review
  22:00 UTC = 11:00 PM CET  — Overnight risk scan
  Weekend:  Saturday 13:00 UTC = 2:00 PM CET — Deep dive
"""

import schedule
import time
import subprocess
import logging
import threading
from datetime import datetime
from flask import Flask

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/daemon.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------
health_app = Flask(__name__)

@health_app.route("/health")
def health():
    return {
        "status": "ok",
        "service": "SNIPER",
        "next_run": str(schedule.next_run()),
        "timestamp": datetime.utcnow().isoformat(),
    }, 200

def start_health_server():
    health_app.run(host="0.0.0.0", port=8080, use_reloader=False)

# ---------------------------------------------------------------------------
# Agent runner
# ---------------------------------------------------------------------------
PYTHON = "/opt/trading-bot/venv/bin/python"
AGENT = "/opt/trading-bot/agent.py"

def run_agent(command: str):
    """Run agent.py with the specified command."""
    logger.info(f"Triggering: {command}")
    try:
        result = subprocess.run(
            [PYTHON, AGENT, command],
            capture_output=True, text=True, timeout=600,
        )
        if result.returncode != 0:
            logger.error(f"agent.py {command} FAILED:\n{result.stderr}")
        else:
            logger.info(f"{command} completed successfully")
    except subprocess.TimeoutExpired:
        logger.error(f"{command} timed out after 600s")
    except Exception as e:
        logger.error(f"Error running {command}: {e}")

# ---------------------------------------------------------------------------
# Schedule — Weekday briefings (Mon-Fri)
# ---------------------------------------------------------------------------
# Full briefings (sonar-pro) — detailed analysis
FULL_BRIEFING_TIMES = ["06:00", "08:00", "12:30", "20:15"]

# Quick updates (sonar) — fast mid-session checks
QUICK_UPDATE_TIMES = ["10:00", "14:30", "16:00", "18:00", "22:00"]

for day in ["monday", "tuesday", "wednesday", "thursday", "friday"]:
    for t in FULL_BRIEFING_TIMES:
        if t == "20:15":
            getattr(schedule.every(), day).at(t).do(run_agent, "eod")
        else:
            getattr(schedule.every(), day).at(t).do(run_agent, "pre-market")

    for t in QUICK_UPDATE_TIMES:
        getattr(schedule.every(), day).at(t).do(run_agent, "intraday")

# Weekend deep dive — Saturday
schedule.every().saturday.at("13:00").do(run_agent, "weekend")

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    threading.Thread(target=start_health_server, daemon=True).start()
    logger.info("Health server started on :8080")

    logger.info("SNIPER daemon started. Enhanced schedule active.")
    logger.info(f"Weekday: {len(FULL_BRIEFING_TIMES)} full briefings + {len(QUICK_UPDATE_TIMES)} quick updates = {len(FULL_BRIEFING_TIMES) + len(QUICK_UPDATE_TIMES)} per day")
    logger.info(f"Next run: {schedule.next_run()}")

    while True:
        schedule.run_pending()
        time.sleep(30)
