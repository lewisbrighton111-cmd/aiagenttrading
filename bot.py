#!/usr/bin/env python3
"""
SNIPER — Telegram Bot (long-polling)
Handles commands for position tracking and manual briefing triggers.

Commands:
  /long  ASSET PRICE [sl:PRICE] [tp:PRICE] [size:QTY] [notes]
  /short ASSET PRICE [sl:PRICE] [tp:PRICE] [size:QTY] [notes]
  /close ASSET [at:PRICE]   or   /close #ID [at:PRICE]
  /positions                 — show all open positions
  /history                   — show recently closed positions
  /run pre-market|intraday|eod|weekend   — trigger a briefing now
  /help                      — show command reference
"""

import os
import re
import logging
import subprocess
import requests
from dotenv import load_dotenv
from positions import (
    open_position, close_position,
    get_open_positions, get_closed_positions,
    format_positions_for_telegram,
)

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

PYTHON = "/opt/trading-bot/venv/bin/python"
AGENT = "/opt/trading-bot/agent.py"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/bot.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def send_message(chat_id: str, text: str):
    """Send a Telegram message."""
    MAX_LEN = 4000
    chunks = []
    if len(text) > MAX_LEN:
        lines = text.split("\n")
        chunk = ""
        for line in lines:
            if len(chunk) + len(line) + 1 > MAX_LEN:
                chunks.append(chunk)
                chunk = line
            else:
                chunk += ("\n" if chunk else "") + line
        if chunk:
            chunks.append(chunk)
    else:
        chunks = [text]

    for chunk in chunks:
        payload = {"chat_id": chat_id, "text": chunk, "parse_mode": "Markdown"}
        try:
            resp = requests.post(f"{API_BASE}/sendMessage", data=payload, timeout=30)
            if resp.status_code == 400 and "parse" in resp.text.lower():
                payload.pop("parse_mode")
                requests.post(f"{API_BASE}/sendMessage", data=payload, timeout=30)
        except Exception as e:
            logger.error(f"Send error: {e}")


def parse_trade_command(text: str) -> dict:
    """
    Parse: /long ETH 2300 sl:2200 tp:2500 size:0.5 momentum play
    Returns dict with asset, price, sl, tp, size, notes
    """
    parts = text.strip().split()
    if len(parts) < 3:
        return None

    result = {"asset": parts[1].upper(), "price": None, "sl": None,
              "tp": None, "size": None, "notes": None}

    try:
        result["price"] = float(parts[2])
    except ValueError:
        return None

    note_parts = []
    for part in parts[3:]:
        p = part.lower()
        if p.startswith("sl:"):
            try:
                result["sl"] = float(p[3:])
            except ValueError:
                pass
        elif p.startswith("tp:"):
            try:
                result["tp"] = float(p[3:])
            except ValueError:
                pass
        elif p.startswith("size:"):
            try:
                result["size"] = float(p[5:])
            except ValueError:
                pass
        else:
            note_parts.append(part)

    if note_parts:
        result["notes"] = " ".join(note_parts)

    return result


def parse_close_command(text: str) -> dict:
    """
    Parse: /close ETH at:2400   or   /close #3 at:2400
    """
    parts = text.strip().split()
    if len(parts) < 2:
        return None

    result = {"asset": None, "pos_id": None, "exit_price": None}

    target = parts[1]
    if target.startswith("#"):
        try:
            result["pos_id"] = int(target[1:])
        except ValueError:
            return None
    else:
        result["asset"] = target.upper()

    for part in parts[2:]:
        if part.lower().startswith("at:"):
            try:
                result["exit_price"] = float(part[3:])
            except ValueError:
                pass

    return result


def handle_message(message: dict):
    """Process an incoming Telegram message."""
    chat_id = str(message["chat"]["id"])
    text = message.get("text", "").strip()

    if not text or not text.startswith("/"):
        return

    # Only respond to the authorized chat
    if chat_id != TELEGRAM_CHAT_ID:
        logger.warning(f"Unauthorized chat: {chat_id}")
        return

    cmd = text.split()[0].lower().split("@")[0]  # handle @botname suffix
    logger.info(f"Command: {text}")

    # --- /long and /short ---
    if cmd in ("/long", "/short"):
        parsed = parse_trade_command(text)
        if not parsed:
            send_message(chat_id,
                         "Usage: `/long ASSET PRICE [sl:PRICE] [tp:PRICE] [size:QTY] [notes]`")
            return

        direction = "LONG" if cmd == "/long" else "SHORT"
        pos_id = open_position(
            asset=parsed["asset"],
            direction=direction,
            entry_price=parsed["price"],
            stop_loss=parsed["sl"],
            take_profit=parsed["tp"],
            size=parsed["size"],
            notes=parsed["notes"],
        )
        emoji = "\U0001f7e2" if direction == "LONG" else "\U0001f534"
        msg = f"{emoji} *Position #{pos_id} opened*\n"
        msg += f"{direction} {parsed['asset']} @ {parsed['price']}"
        if parsed["sl"]:
            msg += f"\nSL: {parsed['sl']}"
        if parsed["tp"]:
            msg += f"\nTP: {parsed['tp']}"
        if parsed["size"]:
            msg += f"\nSize: {parsed['size']}"
        if parsed["notes"]:
            msg += f"\n_{parsed['notes']}_"
        send_message(chat_id, msg)

    # --- /close ---
    elif cmd == "/close":
        parsed = parse_close_command(text)
        if not parsed:
            send_message(chat_id, "Usage: `/close ASSET [at:PRICE]` or `/close #ID [at:PRICE]`")
            return

        closed = close_position(
            asset=parsed["asset"],
            pos_id=parsed["pos_id"],
            exit_price=parsed["exit_price"],
        )
        if not closed:
            send_message(chat_id, "No open position found.")
            return

        for c in closed:
            msg = f"\u2705 *Position #{c['id']} closed*\n"
            msg += f"{c['direction']} {c['asset']} @ {c['entry_price']}"
            if c["exit_price"]:
                msg += f" → {c['exit_price']}"
            if c["pnl_pct"] is not None:
                emoji = "\U0001f4b0" if c["pnl_pct"] >= 0 else "\U0001f4c9"
                msg += f"\n{emoji} P&L: {c['pnl_pct']:+.2f}%"
            send_message(chat_id, msg)

    # --- /positions ---
    elif cmd == "/positions":
        positions = get_open_positions()
        if not positions:
            send_message(chat_id, "No open positions.")
            return
        header = f"\U0001f4bc *Open Positions ({len(positions)})*\n\n"
        send_message(chat_id, header + format_positions_for_telegram())

    # --- /history ---
    elif cmd == "/history":
        closed = get_closed_positions(limit=10)
        if not closed:
            send_message(chat_id, "No trade history yet.")
            return
        lines = [f"\U0001f4d6 *Recent Trades (last {len(closed)})*\n"]
        for p in closed:
            emoji = "\U0001f4b0" if (p.get("pnl") or 0) >= 0 else "\U0001f4c9"
            pnl_str = f"{p['pnl']:+.2f}%" if p.get("pnl") is not None else "N/A"
            lines.append(
                f"{emoji} #{p['id']} {p['direction']} {p['asset']} "
                f"@ {p['entry_price']} → {pnl_str}"
            )
        send_message(chat_id, "\n".join(lines))

    # --- /run ---
    elif cmd == "/run":
        parts = text.split()
        valid = ["pre-market", "intraday", "eod", "weekend"]
        if len(parts) < 2 or parts[1] not in valid:
            send_message(chat_id, f"Usage: `/run {' | '.join(valid)}`")
            return
        briefing = parts[1]
        send_message(chat_id, f"\u23f3 Running {briefing} briefing…")
        try:
            subprocess.Popen(
                [PYTHON, AGENT, briefing],
                cwd="/opt/trading-bot",
            )
        except Exception as e:
            send_message(chat_id, f"Error: {e}")

    # --- /help ---
    elif cmd in ("/help", "/start"):
        help_text = (
            "\U0001f3af *SNIPER Trading Bot*\n\n"
            "*Position Management:*\n"
            "`/long ASSET PRICE [sl:P] [tp:P] [size:Q]`\n"
            "`/short ASSET PRICE [sl:P] [tp:P] [size:Q]`\n"
            "`/close ASSET [at:PRICE]`\n"
            "`/close #ID [at:PRICE]`\n"
            "`/positions` — view open positions\n"
            "`/history` — recent closed trades\n\n"
            "*Briefings:*\n"
            "`/run pre-market` — trigger now\n"
            "`/run intraday` — trigger now\n"
            "`/run eod` — trigger now\n"
            "`/run weekend` — trigger now\n\n"
            "*Examples:*\n"
            "`/long ETH 2300 sl:2200 tp:2500 size:0.5`\n"
            "`/short USDJPY 155.50 sl:156.00 tp:154.00`\n"
            "`/close ETH at:2450`\n"
            "`/close #3 at:155.00`"
        )
        send_message(chat_id, help_text)


def main():
    """Long-polling loop to receive Telegram updates."""
    logger.info("SNIPER Telegram bot started (long-polling)…")
    offset = None

    while True:
        try:
            params = {"timeout": 30, "allowed_updates": ["message"]}
            if offset:
                params["offset"] = offset

            resp = requests.get(
                f"{API_BASE}/getUpdates", params=params, timeout=35
            )
            resp.raise_for_status()
            updates = resp.json().get("result", [])

            for update in updates:
                offset = update["update_id"] + 1
                if "message" in update:
                    handle_message(update["message"])

        except requests.exceptions.Timeout:
            continue
        except Exception as e:
            logger.error(f"Polling error: {e}")
            import time
            time.sleep(5)


if __name__ == "__main__":
    main()
