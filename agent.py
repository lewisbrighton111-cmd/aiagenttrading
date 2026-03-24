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
from positions import format_positions_for_prompt

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
    "CRITICAL: You MUST search for and provide current real-time prices for EVERY instrument mentioned. "
    "Search financial sites like TradingView, Investing.com, MarketWatch, Yahoo Finance, Bloomberg, "
    "CoinGecko, CoinMarketCap, ForexFactory, and Reuters for live price data. "
    "For EVERY instrument, provide the actual current price, daily change, and percentage change. "
    "Be precise with numbers — always cite price levels, percentages, and times. "
    "Use clean formatting with headers and bullet points. "
    "Every trade idea MUST include a specific entry price, stop-loss, take-profit, and risk-reward ratio. "
    "Give clear directional views with conviction levels. Never say data is unavailable — search harder."
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
        "search_domain_filter": [
            "tradingview.com", "investing.com", "marketwatch.com",
            "finance.yahoo.com", "bloomberg.com", "reuters.com",
            "coinmarketcap.com", "coingecko.com", "forexfactory.com",
            "cnbc.com", "wsj.com", "fxstreet.com",
        ],
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
    pos_context = format_positions_for_prompt()
    prompt = f"""Search for CURRENT LIVE PRICES for all instruments listed below and deliver a pre-market intelligence briefing.

{pos_context}
Analyze how current positions are affected by overnight developments. For each open position, provide specific stop/target adjustment recommendations.

You MUST search for and report the exact current price for EACH of these instruments:

FOREX: {', '.join(FOREX)} — search "EUR/USD price today", "USD/JPY live rate", etc.
CRYPTO: {', '.join(CRYPTO)} — search "Bitcoin price", "Ethereum price today", etc.
INDICES: {', '.join(INDICES)} — search "S&P 500 futures", "DAX 40 live", "Nasdaq futures today", etc.
COMMODITIES: {', '.join(COMMODITIES)} — search "crude oil price today", "WTI oil price", etc.
METALS: {', '.join(METALS)} — search "gold price today", "silver price per ounce", etc.

Also search for: "DXY dollar index today", "VIX index today", "economic calendar today"

Structure your response EXACTLY as follows:

1. MARKET REGIME OVERVIEW
   - Global macro regime: risk-on / risk-off / mixed
   - Key overnight developments (Asia, Europe sessions)
   - US Dollar Index (DXY): exact current level, daily change %

2. FOREX OUTLOOK
   For each pair ({', '.join(FOREX)}):
   - EXACT current price and daily change %
   - Key support and resistance levels
   - Directional bias and catalyst

3. CRYPTO OUTLOOK
   For each ({', '.join(CRYPTO)}):
   - EXACT current price and 24h change %
   - Key levels, on-chain signals if notable
   - Directional bias

4. INDICES OUTLOOK
   For each ({', '.join(INDICES)}):
   - EXACT current futures price / pre-market level and daily change %
   - Key levels
   - Sector leadership and notable movers

5. COMMODITIES & METALS
   For each ({', '.join(COMMODITIES + METALS)}):
   - EXACT current price and daily change %
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
   - SPECIFIC entry price based on current market price
   - Stop-loss level and reasoning
   - Take-profit target(s)
   - Risk:Reward ratio
   - Confidence: High / Medium / Low
   - Timeframe: Intraday / Swing

8. RISK DASHBOARD
   - VIX: exact current level and trend
   - Key correlations to watch today
   - Tail risk events

Do NOT say prices are unavailable. You MUST search and find them."""

    result = call_perplexity(prompt, MODEL_BRIEFING, "day")
    header = (
        "\U0001f4cb *SNIPER Pre-Market Briefing*\n"
        f"_{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}_\n\n"
    )
    send_telegram(header + (result or "Error: pre-market briefing failed."))


def intraday_update():
    """Midday update: developments, level checks, flow."""
    logger.info("Running INTRADAY update…")
    pos_context = format_positions_for_prompt()
    prompt = f"""Search for the CURRENT LIVE PRICES right now for all of these instruments and provide an intraday trading update.

{pos_context}
For each open position, assess whether it should be held, scaled, or closed based on current price action.

You MUST look up and report the current price for EACH of these:

FOREX: {', '.join(FOREX)} — search "EUR/USD price today", "GBP/USD live rate", etc.
CRYPTO: {', '.join(CRYPTO)} — search "Bitcoin price", "ETH price today", etc.
INDICES: {', '.join(INDICES)} — search "S&P 500 today", "DAX 40 live", etc.
COMMODITIES: {', '.join(COMMODITIES)} — search "crude oil price today", "natural gas price", etc.
METALS: {', '.join(METALS)} — search "gold price today", "silver price live", etc.

For EVERY instrument, you MUST provide: current price, daily change, and % change.

Then cover:

1. MARKET SNAPSHOT
   - Biggest movers up and down across all asset classes with exact prices and % changes

2. FOREX UPDATE
   - DXY current level and direction
   - Each pair: current bid price, daily change %, key level proximity

3. CRYPTO UPDATE
   - BTC and ETH: exact price, 24h change %, key levels
   - SOL, XRP: price and notable moves

4. INDICES
   - Each index: current level, daily change %, intraday trend

5. COMMODITIES & METALS
   - Each: current price, daily change %
   - Any supply/demand news driving moves

6. KEY DEVELOPMENTS
   - News, data releases, or events moving markets right now

7. TRADE IDEAS
   - 2-3 actionable setups based on current price action
   - Each with: entry price, stop-loss, take-profit, R:R ratio

Do NOT say prices are unavailable. Search for them."""

    result = call_perplexity(prompt, MODEL_QUICK, "hour")
    header = (
        "\u26a1 *SNIPER Intraday Update*\n"
        f"_{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}_\n\n"
    )
    send_telegram(header + (result or "Error: intraday update failed."))


def eod_review():
    """End-of-day review: scorecard, thesis check, overnight risk."""
    logger.info("Running EOD review…")
    pos_context = format_positions_for_prompt()
    prompt = f"""Search for TODAY'S CLOSING PRICES and daily performance for all instruments below and deliver an end-of-day review.

{pos_context}
For each open position, provide an updated risk assessment, recommended stop adjustments, and whether to hold overnight.

You MUST search for and report today's actual closing/current price for EACH of these:

FOREX: {', '.join(FOREX)} — search "EUR/USD closing price today", "USD/JPY price today", etc.
CRYPTO: {', '.join(CRYPTO)} — search "Bitcoin price", "ETH price today", etc.
INDICES: {', '.join(INDICES)} — search "S&P 500 close today", "DAX close today", etc.
COMMODITIES: {', '.join(COMMODITIES)} — search "crude oil closing price", "WTI price today", etc.
METALS: {', '.join(METALS)} — search "gold price today", "silver close today", etc.

Also search: "VIX close today", "DXY close today", "economic calendar tomorrow"

Structure:

1. DAILY SCOREBOARD
   For each asset class, list:
   - Instrument: Close price | Daily change | Change %
   Highlight the biggest movers in each class.

2. SESSION NARRATIVE
   - What was the dominant theme today?
   - Which asset class led? Which lagged?
   - Any regime shift signals?

3. FOREX WRAP
   - DXY closing level and daily change
   - Each pair: closing price, daily change %, session summary

4. CRYPTO WRAP
   - BTC and ETH: closing price, 24h change %, daily candle analysis
   - Funding rates, open interest changes if available

5. INDICES WRAP
   - Each index: closing level, daily change %
   - Sector performance ranking

6. COMMODITIES & METALS WRAP
   - Each: closing price, daily change %
   - Supply/demand developments

7. OVERNIGHT RISK RADAR
   - Events in the next 12 hours that could gap markets
   - Asian session data releases, central bank speakers

8. TOMORROW PREVIEW
   - Key events and expected levels for tomorrow
   - 2-3 trade ideas for tomorrow with entry, SL, TP, R:R

Do NOT say prices are unavailable. You MUST search and find them."""

    result = call_perplexity(prompt, MODEL_BRIEFING, "day")
    header = (
        "\U0001f4ca *SNIPER EOD Review*\n"
        f"_{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}_\n\n"
    )
    send_telegram(header + (result or "Error: EOD review failed."))


def weekend_deep_dive():
    """Weekly deep dive: regime assessment, scoring, swing ideas."""
    logger.info("Running WEEKEND deep dive…")
    pos_context = format_positions_for_prompt()
    prompt = f"""Search for THIS WEEK'S PRICE DATA for all instruments below and conduct a comprehensive weekly analysis.

{pos_context}
For each open position, provide a weekly outlook and whether the trade thesis is still valid for the coming week.

You MUST search for weekly performance data for EACH of these:

FOREX: {', '.join(FOREX)} — search "EUR/USD weekly performance", "USD/JPY this week", etc.
CRYPTO: {', '.join(CRYPTO)} — search "Bitcoin price this week", "ETH weekly chart", etc.
INDICES: {', '.join(INDICES)} — search "S&P 500 weekly performance", "DAX this week", etc.
COMMODITIES: {', '.join(COMMODITIES)} — search "crude oil price this week", "WTI weekly", etc.
METALS: {', '.join(METALS)} — search "gold price this week", "silver weekly", etc.

Also search: "DXY this week", "VIX this week", "COT report latest", "economic calendar next week"

Provide:

1. WEEKLY REGIME ASSESSMENT
   - Has the macro regime shifted this week? Compare to last week.
   - Rate each asset class: Trending / Ranging / Transitioning
   - Inter-market correlations: what's confirming, what's diverging?

2. WEEKLY PERFORMANCE TABLE
   For each instrument:
   - Weekly open, close, high, low, change % (ACTUAL numbers)
   - Relative strength ranking within each asset class

3. FOREX WEEKLY
   - DXY: weekly close, change %, candle analysis
   - Each pair: weekly close, change %, technical patterns
   - COT positioning if available

4. CRYPTO WEEKLY
   - BTC and ETH: weekly close, change %, candle analysis
   - Dominance trend, institutional flow signals

5. INDICES WEEKLY
   - Each index: weekly close, change %
   - Breadth and volatility analysis

6. COMMODITIES & METALS WEEKLY
   - Each: weekly close, change %
   - Supply/demand balance shifts, inventory data

7. CONSENSUS ERRORS
   - Where is the market consensus wrong?
   - Contrarian opportunities across asset classes

8. SWING TRADE IDEAS (4-6 ideas, multi-day to multi-week hold)
   For EACH:
   - Asset, direction, detailed entry logic with SPECIFIC price
   - Stop-loss with ATR-based reasoning
   - Two target levels (partial exit + full exit)
   - Position sizing suggestion (% of capital)
   - Expected hold time
   - Risk:Reward ratio

9. RISK MANAGEMENT REVIEW
   - Portfolio heat check: if all ideas are taken, total risk exposure
   - Correlation between ideas
   - Suggested maximum simultaneous positions

10. NEXT WEEK CALENDAR
    - Major economic releases with dates, times (UTC), and consensus
    - Central bank decisions or minutes
    - Earnings to watch

Do NOT say prices are unavailable. You MUST search and find them."""

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
