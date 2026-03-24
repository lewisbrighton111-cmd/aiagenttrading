#!/usr/bin/env python3
"""
SNIPER Daemon — Schedule-based runner for trading briefings.
All times are UTC.  Adjust the constants below to shift your schedule.

Default schedule (UTC → CET → ET):
  Pre-market:  12:30 UTC  =  1:30 PM CET  =  8:30 AM ET
  Intraday:    16:00 UTC  =  5:00 PM CET  = 12:00 PM ET
  EOD:         20:15 UTC  =  9:15 PM CET  =  4:15 PM ET
  Weekend:     13:00 UTC Saturday  =  2:00 PM CET  =  9:00 AM ET
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
# Health endpoint (for UptimeRobot or similar)
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
AGENT  = "/opt/trading-bot/agent.py"

def run_agent(command: str):
    """Run agent.py with the specified command."""
    logger.info(f"Triggering: {command}")
    try:
        result = subprocess.run(
            [PYTHON, AGENT, command],
            capture_output=True,
            text=True,
            timeout=600,          # 10 min hard timeout (deep dive can be slow)
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
# Schedule — weekday briefings (Mon-Fri)
# ---------------------------------------------------------------------------
for day in ["monday", "tuesday", "wednesday", "thursday", "friday"]:
    getattr(schedule.every(), day).at("12:30").do(run_agent, "pre-market")
    getattr(schedule.every(), day).at("16:00").do(run_agent, "intraday")
    getattr(schedule.every(), day).at("20:15").do(run_agent, "eod")

# Weekend deep dive — Saturday
schedule.every().saturday.at("13:00").do(run_agent, "weekend")

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Start health server in background thread
    threading.Thread(target=start_health_server, daemon=True).start()
    logger.info("Health server started on :8080")

    logger.info("SNIPER daemon started. Waiting for scheduled tasks…")
    logger.info(f"Next run: {schedule.next_run()}")

    while True:
        schedule.run_pending()
        time.sleep(30)
