#!/usr/bin/env python3
"""
SNIPER — Position Tracker (SQLite)
Stores open/closed trades so briefings can reference your actual portfolio.
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "positions.db")


def get_db():
    """Get a database connection, creating tables if needed."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset TEXT NOT NULL,
            direction TEXT NOT NULL,          -- LONG or SHORT
            entry_price REAL NOT NULL,
            stop_loss REAL,
            take_profit REAL,
            size REAL,
            status TEXT DEFAULT 'OPEN',       -- OPEN or CLOSED
            pnl REAL,
            opened_at TEXT NOT NULL,
            closed_at TEXT,
            notes TEXT
        )
    """)
    conn.commit()
    return conn


def open_position(asset: str, direction: str, entry_price: float,
                  stop_loss: float = None, take_profit: float = None,
                  size: float = None, notes: str = None) -> int:
    """Open a new position. Returns the position ID."""
    conn = get_db()
    cur = conn.execute(
        """INSERT INTO positions
           (asset, direction, entry_price, stop_loss, take_profit, size, opened_at, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (asset.upper(), direction.upper(), entry_price, stop_loss,
         take_profit, size, datetime.utcnow().isoformat(), notes)
    )
    conn.commit()
    pos_id = cur.lastrowid
    conn.close()
    return pos_id


def close_position(asset: str = None, pos_id: int = None,
                   exit_price: float = None) -> list[dict]:
    """Close position(s) by asset name or ID. Returns list of closed positions."""
    conn = get_db()
    closed = []

    if pos_id:
        rows = conn.execute(
            "SELECT * FROM positions WHERE id = ? AND status = 'OPEN'", (pos_id,)
        ).fetchall()
    elif asset:
        rows = conn.execute(
            "SELECT * FROM positions WHERE UPPER(asset) = ? AND status = 'OPEN'",
            (asset.upper(),)
        ).fetchall()
    else:
        return []

    for row in rows:
        pnl = None
        if exit_price and row["entry_price"]:
            if row["direction"] == "LONG":
                pnl = round((exit_price - row["entry_price"]) / row["entry_price"] * 100, 2)
            else:
                pnl = round((row["entry_price"] - exit_price) / row["entry_price"] * 100, 2)

        conn.execute(
            """UPDATE positions
               SET status = 'CLOSED', closed_at = ?, pnl = ?
               WHERE id = ?""",
            (datetime.utcnow().isoformat(), pnl, row["id"])
        )
        closed.append({
            "id": row["id"],
            "asset": row["asset"],
            "direction": row["direction"],
            "entry_price": row["entry_price"],
            "exit_price": exit_price,
            "pnl_pct": pnl,
        })

    conn.commit()
    conn.close()
    return closed


def get_open_positions() -> list[dict]:
    """Return all open positions."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM positions WHERE status = 'OPEN' ORDER BY opened_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_closed_positions(limit: int = 20) -> list[dict]:
    """Return recently closed positions."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM positions WHERE status = 'CLOSED' ORDER BY closed_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def format_positions_for_prompt() -> str:
    """Format open positions as a text block to inject into AI prompts."""
    positions = get_open_positions()
    if not positions:
        return "No open positions."

    lines = ["CURRENT OPEN POSITIONS:"]
    for p in positions:
        line = f"  #{p['id']} {p['direction']} {p['asset']} @ {p['entry_price']}"
        if p.get("stop_loss"):
            line += f" | SL: {p['stop_loss']}"
        if p.get("take_profit"):
            line += f" | TP: {p['take_profit']}"
        if p.get("size"):
            line += f" | Size: {p['size']}"
        if p.get("notes"):
            line += f" | {p['notes']}"
        lines.append(line)

    return "\n".join(lines)


def format_positions_for_telegram() -> str:
    """Format open positions for Telegram display."""
    positions = get_open_positions()
    if not positions:
        return "No open positions."

    lines = []
    for p in positions:
        emoji = "\U0001f7e2" if p["direction"] == "LONG" else "\U0001f534"
        line = f"{emoji} #{p['id']} *{p['direction']} {p['asset']}* @ {p['entry_price']}"
        details = []
        if p.get("stop_loss"):
            details.append(f"SL: {p['stop_loss']}")
        if p.get("take_profit"):
            details.append(f"TP: {p['take_profit']}")
        if p.get("size"):
            details.append(f"Size: {p['size']}")
        if details:
            line += "\n   " + " | ".join(details)
        if p.get("notes"):
            line += f"\n   {p['notes']}"
        lines.append(line)

    return "\n\n".join(lines)
