"""
Tasks Module

后台任务管理
"""

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Optional, Dict, Any

# Global trending cache (shared with routes)
trending_cache: list = []


def _update_trending_cache():
    """Update trending cache - calculates from positions table."""
    global trending_cache
    from database import get_db_connection
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get symbols ranked by holder count with current prices
    cursor.execute("""
        SELECT symbol, market, token_id, outcome, COUNT(DISTINCT agent_id) as holder_count
        FROM positions
        GROUP BY symbol, market, token_id, outcome
        ORDER BY holder_count DESC
        LIMIT 20
    """)
    rows = cursor.fetchall()

    trending_cache = []
    for row in rows:
        # Get current price from positions table
        cursor.execute("""
            SELECT current_price FROM positions
            WHERE symbol = ? AND market = ? AND COALESCE(token_id, '') = COALESCE(?, '')
            LIMIT 1
        """, (row["symbol"], row["market"], row["token_id"]))
        price_row = cursor.fetchone()

        trending_cache.append({
            "symbol": row["symbol"],
            "market": row["market"],
            "token_id": row["token_id"],
            "outcome": row["outcome"],
            "holder_count": row["holder_count"],
            "current_price": price_row["current_price"] if price_row else None
        })

    conn.close()


async def update_position_prices():
    """Background task to update position prices every 5 minutes."""
    from database import get_db_connection
    from price_fetcher import get_price_from_market

    # Get max parallel requests from environment variable
    max_parallel = int(os.getenv("MAX_PARALLEL_PRICE_FETCH", "5"))

    # Wait a bit on startup before first update
    await asyncio.sleep(5)

    while True:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # Get all unique positions with symbol and market
            cursor.execute("""
                SELECT DISTINCT symbol, market, token_id, outcome
                FROM positions
            """)
            unique_positions = cursor.fetchall()

            print(f"[Price Update] Found {len(unique_positions)} positions to update")

            # Semaphore to control concurrency
            semaphore = asyncio.Semaphore(max_parallel)

            async def fetch_and_update(row):
                symbol = row["symbol"]
                market = row["market"]
                token_id = row["token_id"]
                outcome = row["outcome"]

                async with semaphore:
                    # Run synchronous function in thread pool
                    # Use UTC time for consistent pricing timestamps
                    now = datetime.now(timezone.utc)
                    executed_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
                    price = await asyncio.to_thread(
                        get_price_from_market, symbol, executed_at, market, token_id, outcome
                    )

                    if price:
                        # Update all positions with this symbol/market
                        conn2 = get_db_connection()
                        cursor2 = conn2.cursor()
                        cursor2.execute("""
                            UPDATE positions
                            SET current_price = ?
                            WHERE symbol = ? AND market = ? AND COALESCE(token_id, '') = COALESCE(?, '')
                        """, (price, symbol, market, token_id))
                        conn2.commit()
                        conn2.close()
                        print(f"[Price Update] {symbol} ({market}, token={token_id or '-'}): ${price}")
                    else:
                        print(f"[Price Update] Failed to get price for {symbol} ({market}, token={token_id or '-'})")

                return price

            # Run all fetches in parallel
            await asyncio.gather(*[fetch_and_update(row) for row in unique_positions])

            conn.close()

            # Update trending cache (no additional API call, uses same data)
            _update_trending_cache()

        except Exception as e:
            print(f"[Price Update Error] {e}")

        # Wait interval from environment variable (default: 5 minutes = 300 seconds)
        refresh_interval = int(os.getenv("POSITION_REFRESH_INTERVAL", "300"))
        print(f"[Price Update] Next update in {refresh_interval} seconds")
        await asyncio.sleep(refresh_interval)


async def periodic_token_cleanup():
    """Periodically clean up expired tokens."""
    from utils import cleanup_expired_tokens

    while True:
        try:
            await asyncio.sleep(3600)  # Every hour
            deleted = cleanup_expired_tokens()
            if deleted > 0:
                print(f"[Token Cleanup] Cleaned up {deleted} expired tokens")
        except Exception as e:
            print(f"[Token Cleanup Error] {e}")


async def record_profit_history():
    """Record profit history for all agents."""
    from database import get_db_connection
    from price_fetcher import get_price_from_market

    print("[Profit History] Task starting...")

    while True:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # Get all agents with their cash and positions
            cursor.execute("""
                SELECT id, cash, deposited FROM agents
            """)
            agents = cursor.fetchall()
            print(f"[Profit History] Found {len(agents)} agents")

            for idx, agent in enumerate(agents):
                agent_id = agent["id"]
                cash = agent["cash"] or 0
                deposited = agent["deposited"] or 0
                initial_capital = 100000.0

                # Calculate position value
                cursor.execute("""
                    SELECT quantity, current_price, entry_price, side
                    FROM positions
                    WHERE agent_id = ?
                """, (agent_id,))
                positions = cursor.fetchall()

                position_value = 0
                for pos in positions:
                    if pos["current_price"]:
                        if pos["side"] == "long":
                            position_value += pos["current_price"] * abs(pos["quantity"])
                        else:  # short
                            position_value += pos["entry_price"] * abs(pos["quantity"])

                # Calculate profit: (cash + position) - (initial + deposited)
                # This excludes deposited cash from profit calculation
                total_value = cash + position_value
                profit = total_value - (initial_capital + deposited)
                # Clamp profit to avoid absurd values (e.g. from bad Polymarket price or API noise)
                _max_abs_profit = 1e12
                if abs(profit) > _max_abs_profit:
                    print(f"[Profit History] Agent {agent_id}: clamping absurd profit {profit} to ±{_max_abs_profit}")
                    profit = _max_abs_profit if profit > 0 else -_max_abs_profit
                # Avoid per-agent logging (too noisy, can starve the event loop under load)

                # Record history
                now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                cursor.execute("""
                    INSERT INTO profit_history (agent_id, total_value, cash, position_value, profit, recorded_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (agent_id, total_value, cash, position_value, profit, now))

                # Yield to the event loop periodically so API remains responsive
                if idx % 25 == 0:
                    await asyncio.sleep(0)

            conn.commit()
            conn.close()
            print(f"[Profit History] Recorded profit for {len(agents)} agents")

        except Exception as e:
            print(f"[Profit History Error] {e}")

        # Record at the same interval as position refresh (controlled by POSITION_REFRESH_INTERVAL)
        refresh_interval = int(os.getenv("POSITION_REFRESH_INTERVAL", "300"))
        await asyncio.sleep(refresh_interval)


async def settle_polymarket_positions():
    """
    Background task to auto-settle resolved Polymarket positions.

    When a Polymarket market resolves, Gamma exposes `resolved` and `settlementPrice`.
    We treat each held outcome token as explicit spot-like inventory:
    - proceeds = quantity * settlementPrice
    - credit proceeds to agent cash
    - record an immutable settlement ledger entry
    - delete the position
    """
    from database import get_db_connection
    from price_fetcher import _polymarket_resolve

    # Wait a bit on startup before first settle pass
    await asyncio.sleep(10)

    while True:
        try:
            interval_s = int(os.getenv("POLYMARKET_SETTLE_INTERVAL", "60"))
        except Exception:
            interval_s = 60

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, agent_id, symbol, token_id, outcome, quantity, entry_price
                FROM positions
                WHERE market = 'polymarket'
            """)
            rows = cursor.fetchall()

            settled = 0
            skipped = 0

            for row in rows:
                pos_id = row["id"]
                agent_id = row["agent_id"]
                symbol = row["symbol"]
                token_id = row["token_id"]
                outcome = row["outcome"]
                qty = row["quantity"] or 0

                if not token_id:
                    skipped += 1
                    continue

                resolution = _polymarket_resolve(symbol, token_id=token_id, outcome=outcome)
                if not resolution or not resolution.get("resolved"):
                    skipped += 1
                    continue

                settlement_price = resolution.get("settlementPrice")
                if settlement_price is None:
                    skipped += 1
                    continue

                proceeds = float(f"{(abs(qty) * float(settlement_price)):.6f}")

                # Apply settlement atomically
                cursor.execute("UPDATE agents SET cash = cash + ? WHERE id = ?", (proceeds, agent_id))
                cursor.execute("""
                    INSERT INTO polymarket_settlements
                    (position_id, agent_id, symbol, token_id, outcome, quantity, entry_price, settlement_price, proceeds, market_slug, resolved_outcome, resolved_at, source_data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    pos_id,
                    agent_id,
                    symbol,
                    token_id,
                    outcome,
                    qty,
                    row["entry_price"],
                    settlement_price,
                    proceeds,
                    resolution.get("market_slug"),
                    resolution.get("resolved_outcome"),
                    datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    json.dumps(resolution),
                ))
                cursor.execute("DELETE FROM positions WHERE id = ?", (pos_id,))
                settled += 1

            conn.commit()
            conn.close()
            if settled > 0:
                print(f"[Polymarket Settler] settled={settled}, skipped={skipped}")

        except Exception as e:
            try:
                conn.close()
            except Exception:
                pass
            print(f"[Polymarket Settler Error] {e}")

        await asyncio.sleep(interval_s)
