"""
Tasks Module

后台任务管理
"""

import asyncio
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
        SELECT symbol, market, COUNT(DISTINCT agent_id) as holder_count
        FROM positions
        GROUP BY symbol, market
        ORDER BY holder_count DESC
        LIMIT 20
    """)
    rows = cursor.fetchall()

    trending_cache = []
    for row in rows:
        # Get current price from positions table
        cursor.execute("""
            SELECT current_price FROM positions
            WHERE symbol = ? AND market = ?
            LIMIT 1
        """, (row["symbol"], row["market"]))
        price_row = cursor.fetchone()

        trending_cache.append({
            "symbol": row["symbol"],
            "market": row["market"],
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
                SELECT DISTINCT symbol, market
                FROM positions
            """)
            unique_positions = cursor.fetchall()

            print(f"[Price Update] Found {len(unique_positions)} positions to update")

            # Semaphore to control concurrency
            semaphore = asyncio.Semaphore(max_parallel)

            async def fetch_and_update(row):
                symbol = row["symbol"]
                market = row["market"]

                async with semaphore:
                    # Run synchronous function in thread pool
                    # Use UTC time since Alpha Vantage returns UTC
                    now = datetime.now(timezone.utc)
                    executed_at = now.strftime("%Y-%m-%dT%H:%M:%S")
                    price = await asyncio.to_thread(
                        get_price_from_market, symbol, executed_at, market
                    )

                    if price:
                        # Update all positions with this symbol/market
                        conn2 = get_db_connection()
                        cursor2 = conn2.cursor()
                        cursor2.execute("""
                            UPDATE positions
                            SET current_price = ?
                            WHERE symbol = ? AND market = ?
                        """, (price, symbol, market))
                        conn2.commit()
                        conn2.close()
                        print(f"[Price Update] {symbol} ({market}): ${price}")
                    else:
                        print(f"[Price Update] Failed to get price for {symbol} ({market})")

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

            for agent in agents:
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
                print(f"[Profit History] Agent {agent_id}: cash={cash}, pos_value={position_value}, profit={profit}")

                # Record history
                now = datetime.now(timezone.utc).isoformat()
                cursor.execute("""
                    INSERT INTO profit_history (agent_id, total_value, cash, position_value, profit, recorded_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (agent_id, total_value, cash, position_value, profit, now))

            conn.commit()
            conn.close()
            print(f"[Profit History] Recorded profit for {len(agents)} agents")

        except Exception as e:
            print(f"[Profit History Error] {e}")

        # Record at the same interval as position refresh (controlled by POSITION_REFRESH_INTERVAL)
        refresh_interval = int(os.getenv("POSITION_REFRESH_INTERVAL", "300"))
        await asyncio.sleep(refresh_interval)
