#!/usr/bin/env python3
"""
SNIPER - Self-hosted Networked Intelligence Pipeline for Execution Research
Main agent script: calls Perplexity Sonar API, sends results to Telegram.

Asset classes covered:
  - Forex: EUR/USD, GBP/USD, USD/JPY, AUD/USD, USD/CHF, USD/CAD
  - Crypto: BTC/USD, ETH/USD, SOL/USD, XRP/USD
  - Indices: S&P 500, Nasdaq 100, Dow Jones, DAX 40, FTSE 100, Nikkei 225
  - Commodities: Crude Oil (WTI), Natural Gas, Wheat, Corn
  - Metals: Gold (XAU/USD), Silver (XAG/USD), Platinum, Copper

Usage:
    python agent.py pre-market
    python agent.py intraday
    python agent.py eod
    python agent.py weekend
"""

import os
import sys
import json
import time
import logging
import requests
from datetime import datetime
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
load_dotenv()

PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

MODEL_BRIEFING = os.getenv("MODEL_BRIEFING", "sonar-pro")
MODEL_QUICK = os.getenv("MODEL_QUICK", "sonar")
MODEL_DEEP = os.getenv("MODEL_DEEP", "sonar-reasoning-pro")

SEARCH_RECENCY = os.getenv("SEARCH_RECENCY", "day")

API_URL = "https://api.perplexity.ai/chat/completions"

# ---------------------------------------------------------------------------
# Instruments — edit these lists to add / remove assets
# ---------------------------------------------------------------------------
FOREX = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CHF", "USD/CAD"]
CRYPTO = ["BTC/USD", "ETH/USD", "SOL/USD", "XRP/USD"]
INDICES = ["S&P 500", "Nasdaq 100", "Dow Jones", "DAX 40", "FTSE 100", "Nikkei 225"]
COMMODITIES = ["Crude Oil (WTI)", "Natural Gas", "Wheat", "Corn"]
METALS = ["Gold (XAU/USD)", "Silver (XAG/USD)", "Platinum", "Copper"]

ALL_INSTRUMENTS = {
    "Forex": FOREX,
    "Crypto": CRYPTO,
    "Indices": INDICES,
    "Commodities": COMMODITIES,
    "Metals": METALS,
}

def instrument_block() -> str:
    """Return a formatted string listing every tracked instrument."""
    lines = []
    for category, instruments in ALL_INSTRUMENTS.items():
        lines.append(f"  {category}: {', '.join(instruments)}")
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/agent.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt — shared across all briefing types
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = (
    "You are SNIPER, a senior multi-asset trading analyst. "
    "You cover forex, crypto, stock indices, commodities, and metals. "
    "Be precise with numbers — always cite price levels, percentages, and times. "
    "Use clean formatting with headers and bullet points. "
    "Every trade idea MUST include entry, stop-loss, take-profit, and risk-reward ratio. "
    "Never hedge excessively — give clear directional views with conviction levels. "
    "If data is unavailable for an instrument, say so instead of guessing."
)

# ---------------------------------------------------------------------------
# Perplexity API caller
# ---------------------------------------------------------------------------
def call_perplexity(prompt: str, model: str, recency_filter: str = "day") -> str | None:
    """Call Perplexity Sonar API with retry logic."""
    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 8192,
        "search_recency_filter": recency_filter,
    }

    for attempt in range(3):
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=180)
            if resp.status_code == 429:
                wait = (2 ** attempt) * 5
                logger.warning(f"Rate limited. Waiting {wait}s…")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            citations = data.get("citations", [])
            usage = data.get("usage", {})
            logger.info(f"API OK | model={model} | tokens={usage}")

            if citations:
                content += "\n\n---\nSources:\n"
                for i, url in enumerate(citations, 1):
                    content += f"{i}. {url}\n"
            return content

        except requests.exceptions.RequestException as e:
            logger.error(f"API error (attempt {attempt + 1}): {e}")
            if attempt < 2:
                time.sleep(2 ** attempt)

    return None


# ---------------------------------------------------------------------------
# Telegram sender
# ---------------------------------------------------------------------------
def send_telegram(message: str) -> bool:
    """Send a message via Telegram Bot API, splitting if needed."""
    if not message:
        logger.warning("Empty message — skipping Telegram send.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    # Telegram limit is 4096 chars — split at line boundaries
    MAX_LEN = 4000
    chunks: list[str] = []
    if len(message) > MAX_LEN:
        lines = message.split("\n")
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
        chunks = [message]

    success = True
    for i, chunk in enumerate(chunks):
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
            "parse_mode": "Markdown",
        }
        try:
            resp = requests.post(url, data=payload, timeout=30)
            if resp.status_code == 400 and "parse" in resp.text.lower():
                # Markdown failed — retry without parse_mode
                payload.pop("parse_mode")
                resp = requests.post(url, data=payload, timeout=30)
            resp.raise_for_status()
            logger.info(f"Telegram sent ({i + 1}/{len(chunks)})")
        except requests.exceptions.RequestException as e:
            logger.error(f"Telegram error: {e}")
            success = False
    return success


# ===================================================================
# BRIEFING TYPES
# ===================================================================

def pre_market_briefing():
    """Pre-market briefing: regime, levels, catalysts, trade ideas."""
    logger.info("Running PRE-MARKET briefing…")
    prompt = f"""Deliver a comprehensive pre-market intelligence briefing for today.

Instruments tracked:
{instrument_block()}

Structure your response EXACTLY as follows:

1. MARKET REGIME OVERVIEW
   - Global macro regime: risk-on / risk-off / mixed
   - Key overnight developments (Asia, Europe sessions)
   - US Dollar Index (DXY) direction and driver

2. FOREX OUTLOOK
   For each pair ({', '.join(FOREX)}):
   - Current price, overnight change %
   - Key support and resistance levels
   - Directional bias and catalyst

3. CRYPTO OUTLOOK
   For each ({', '.join(CRYPTO)}):
   - Current price, 24h change %
   - Key levels, on-chain signals if notable
   - Directional bias

4. INDICES OUTLOOK
   For each ({', '.join(INDICES)}):
   - Futures price / pre-market indication
   - Key levels
   - Sector leadership and notable movers

5. COMMODITIES & METALS
   For each ({', '.join(COMMODITIES + METALS)}):
   - Current price, daily change %
   - Supply/demand drivers, inventory data
   - Key levels

6. MACRO CATALYSTS TODAY
   - Economic data releases with times (UTC) and consensus expectations
   - Central bank speakers
   - Earnings reports
   - Geopolitical events

7. TOP TRADE IDEAS (5-8 ideas across all asset classes)
   For EACH idea:
   - Asset and direction (Long/Short)
   - Entry price and trigger condition
   - Stop-loss level and reasoning
   - Take-profit target(s)
   - Risk:Reward ratio
   - Confidence: High / Medium / Low
   - Timeframe: Intraday / Swing

8. RISK DASHBOARD
   - VIX level and trend
   - Key correlations to watch today
   - Tail risk events"""

    result = call_perplexity(prompt, MODEL_BRIEFING, "day")
    header = (
        "\U0001f4cb *SNIPER Pre-Market Briefing*\n"
        f"_{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}_\n\n"
    )
    send_telegram(header + (result or "Error: pre-market briefing failed."))


def intraday_update():
    """Midday update: developments, level checks, flow."""
    logger.info("Running INTRADAY update…")
    prompt = f"""Provide a concise intraday trading update across all asset classes.

Instruments tracked:
{instrument_block()}

Cover:

1. SESSION SUMMARY SO FAR
   - What moved the most since the open? Biggest winners and losers.
   - Any surprise data releases or headlines?

2. LEVEL CHECK
   - For major movers: are pre-market support/resistance levels holding?
   - Notable breakouts, breakdowns, or rejections

3. FOREX UPDATE
   - DXY move today, major pair updates (focus on pairs that moved >0.3%)

4. CRYPTO UPDATE
   - BTC and ETH price action, dominance shift, notable altcoin moves

5. INDICES & EQUITIES
   - Index performance, sector rotation, notable single-stock moves

6. COMMODITIES & METALS
   - Oil, gold, and any commodity making a significant move

7. FLOW & SENTIMENT
   - Unusual options activity, large block trades
   - Crypto whale movements or exchange flow if notable
   - Put/call ratio changes

8. TRADE IDEA ADJUSTMENTS
   - Should any morning ideas be modified, stopped out, or scaled?
   - Any NEW intraday setups emerging?

Keep it punchy — this is a quick mid-session check, not a full briefing."""

    result = call_perplexity(prompt, MODEL_QUICK, "hour")
    header = (
        "\u26a1 *SNIPER Intraday Update*\n"
        f"_{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}_\n\n"
    )
    send_telegram(header + (result or "Error: intraday update failed."))


def eod_review():
    """End-of-day review: scorecard, thesis check, overnight risk."""
    logger.info("Running EOD review…")
    prompt = f"""Deliver an end-of-day trading review across all asset classes.

Instruments tracked:
{instrument_block()}

Structure:

1. DAILY SCOREBOARD
   For each asset class, provide a table:
   - Instrument | Open | High | Low | Close | Change %
   Focus on the biggest movers in each class.

2. SESSION NARRATIVE
   - What was the dominant theme today?
   - Which asset class led? Which lagged?
   - Any regime shift signals?

3. TRADE IDEA SCORECARD
   - Review typical pre-market trade setups: which levels were hit?
   - What worked and what didn't?
   - Lessons or patterns to note

4. FOREX WRAP
   - DXY close, major pair summaries
   - Any pairs setting up for multi-day moves?

5. CRYPTO WRAP
   - BTC and ETH daily candle analysis
   - Funding rates, open interest changes
   - Notable on-chain data

6. INDICES WRAP
   - Close levels, breadth indicators
   - Sector performance ranking

7. COMMODITIES & METALS WRAP
   - Closing prices, inventory changes
   - Supply/demand developments

8. OVERNIGHT RISK RADAR
   - Events in the next 12 hours that could gap markets
   - Asian session data releases
   - Central bank speakers overnight
   - Geopolitical watch items

9. TOMORROW PREVIEW
   - Key events and expected levels for tomorrow
   - Early trade ideas to research tonight"""

    result = call_perplexity(prompt, MODEL_BRIEFING, "day")
    header = (
        "\U0001f4ca *SNIPER EOD Review*\n"
        f"_{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}_\n\n"
    )
    send_telegram(header + (result or "Error: EOD review failed."))


def weekend_deep_dive():
    """Weekly deep dive: regime assessment, scoring, swing ideas."""
    logger.info("Running WEEKEND deep dive…")
    prompt = f"""Conduct a comprehensive weekly trading analysis across all asset classes.

Instruments tracked:
{instrument_block()}

Provide:

1. WEEKLY REGIME ASSESSMENT
   - Has the macro regime shifted this week? Compare to last week.
   - Rate each asset class: Trending / Ranging / Transitioning
   - Inter-market correlations: what's confirming, what's diverging?

2. WEEKLY PERFORMANCE TABLE
   For each instrument:
   - Weekly open, close, high, low, change %
   - Relative strength ranking within each asset class

3. FOREX WEEKLY
   - DXY weekly candle analysis
   - Major pair weekly closes and technical patterns
   - COT (Commitment of Traders) positioning if available

4. CRYPTO WEEKLY
   - BTC and ETH weekly candle, dominance trend
   - DeFi/NFT/L2 narrative shifts
   - Institutional flow signals

5. INDICES WEEKLY
   - Weekly performance ranking
   - Breadth and volatility analysis
   - Earnings season impact (if applicable)

6. COMMODITIES & METALS WEEKLY
   - Supply/demand balance shifts
   - Seasonal patterns in play
   - Inventory and production data

7. CONSENSUS ERRORS
   - Where is the market consensus wrong?
   - Contrarian opportunities across asset classes

8. SWING TRADE IDEAS (4-6 ideas, multi-day to multi-week hold)
   For EACH:
   - Asset, direction, detailed entry logic and trigger
   - Stop-loss with ATR-based reasoning
   - Two target levels (partial exit + full exit)
   - Position sizing suggestion (% of capital)
   - Expected hold time
   - Risk:Reward ratio

9. RISK MANAGEMENT REVIEW
   - Portfolio heat check: if all ideas are taken, total risk exposure
   - Correlation between ideas — are you concentrated in one theme?
   - Suggested maximum simultaneous positions

10. NEXT WEEK CALENDAR
    - Major economic releases with dates, times (UTC), and consensus
    - Central bank decisions or minutes
    - Earnings to watch
    - Geopolitical events on the radar"""

    result = call_perplexity(prompt, MODEL_DEEP, "week")
    header = (
        "\U0001f9e0 *SNIPER Weekend Deep Dive*\n"
        f"_{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}_\n\n"
    )
    send_telegram(header + (result or "Error: weekend deep dive failed."))


# ===================================================================
# Main entry point
# ===================================================================
def main():
    commands = {
        "pre-market": pre_market_briefing,
        "intraday": intraday_update,
        "eod": eod_review,
        "weekend": weekend_deep_dive,
    }

    if len(sys.argv) < 2 or sys.argv[1] not in commands:
        print(f'Usage: python agent.py <{"|".join(commands.keys())}>')
        sys.exit(1)

    # Validate credentials
    missing = []
    if not PERPLEXITY_API_KEY:
        missing.append("PERPLEXITY_API_KEY")
    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not TELEGRAM_CHAT_ID:
        missing.append("TELEGRAM_CHAT_ID")
    if missing:
        logger.error(f"Missing env vars: {', '.join(missing)}. Check your .env file.")
        sys.exit(1)

    cmd = sys.argv[1]
    logger.info(f"Executing: {cmd}")
    commands[cmd]()
    logger.info("Done.")


if __name__ == "__main__":
    main()
