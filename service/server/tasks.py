"""
Tasks Module

后台任务管理
"""

import asyncio
import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

# Global trending cache (shared with routes)
trending_cache: list = []
_last_profit_history_prune_at: float = 0.0


def _backfill_polymarket_position_metadata() -> None:
    """Best-effort backfill for legacy Polymarket positions missing token_id/outcome."""
    from database import get_db_connection
    from price_fetcher import _polymarket_resolve_reference

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, symbol, token_id, outcome
            FROM positions
            WHERE market = 'polymarket' AND (token_id IS NULL OR token_id = '')
        """)
        rows = cursor.fetchall()
        if not rows:
            conn.close()
            return

        updated = 0
        skipped = 0
        for row in rows:
            outcome = row["outcome"]
            if not outcome:
                skipped += 1
                continue
            contract = _polymarket_resolve_reference(row["symbol"], outcome=outcome)
            if not contract or not contract.get("token_id"):
                skipped += 1
                continue
            cursor.execute("""
                UPDATE positions
                SET token_id = ?, outcome = COALESCE(outcome, ?)
                WHERE id = ?
            """, (contract["token_id"], contract.get("outcome"), row["id"]))
            updated += 1

        if updated > 0:
            conn.commit()
            print(f"[Polymarket Backfill] Updated {updated} legacy positions; skipped={skipped}")
        else:
            conn.rollback()
    finally:
        conn.close()


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


def _prune_profit_history() -> None:
    """Compact profit history so it remains useful for charts without growing forever."""
    from database import get_db_connection, using_postgres

    full_resolution_hours = int(os.getenv("PROFIT_HISTORY_FULL_RESOLUTION_HOURS", "24"))
    compact_window_days = int(os.getenv("PROFIT_HISTORY_COMPACT_WINDOW_DAYS", "7"))
    bucket_minutes = int(os.getenv("PROFIT_HISTORY_COMPACT_BUCKET_MINUTES", "15"))

    if compact_window_days <= 0:
        return

    now = datetime.now(timezone.utc)
    hard_cutoff = (now - timedelta(days=compact_window_days)).isoformat().replace("+00:00", "Z")
    full_resolution_cutoff = (now - timedelta(hours=full_resolution_hours)).isoformat().replace("+00:00", "Z")

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        cursor.execute("DELETE FROM profit_history WHERE recorded_at < ?", (hard_cutoff,))
        deleted_old = cursor.rowcount if cursor.rowcount is not None else 0
        deleted_compacted = 0

        if bucket_minutes > 0 and full_resolution_cutoff > hard_cutoff:
            if using_postgres():
                cursor.execute("""
                    WITH ranked AS (
                        SELECT
                            id,
                            ROW_NUMBER() OVER (
                                PARTITION BY
                                    agent_id,
                                    date_trunc('hour', recorded_at::timestamptz)
                                    + floor(extract(minute FROM recorded_at::timestamptz) / ?) * (? || ' minutes')::interval
                                ORDER BY recorded_at DESC, id DESC
                            ) AS rn
                        FROM profit_history
                        WHERE recorded_at >= ? AND recorded_at < ?
                    )
                    DELETE FROM profit_history ph
                    USING ranked
                    WHERE ph.id = ranked.id AND ranked.rn > 1
                """, (bucket_minutes, bucket_minutes, hard_cutoff, full_resolution_cutoff))
                deleted_compacted = cursor.rowcount if cursor.rowcount is not None else 0
            else:
                cursor.execute("""
                    DELETE FROM profit_history
                    WHERE id IN (
                        SELECT id
                        FROM (
                            SELECT
                                id,
                                ROW_NUMBER() OVER (
                                    PARTITION BY
                                        agent_id,
                                        strftime('%Y-%m-%dT%H', recorded_at),
                                        CAST(strftime('%M', recorded_at) AS INTEGER) / ?
                                    ORDER BY recorded_at DESC, id DESC
                                ) AS rn
                            FROM profit_history
                            WHERE recorded_at >= ? AND recorded_at < ?
                        ) ranked
                        WHERE rn > 1
                    )
                """, (bucket_minutes, hard_cutoff, full_resolution_cutoff))
                deleted_compacted = cursor.rowcount if cursor.rowcount is not None else 0

        conn.commit()
        if deleted_old or deleted_compacted:
            print(
                "[Profit History] Pruned history: "
                f"deleted_old={deleted_old} compacted={deleted_compacted}"
            )
    finally:
        conn.close()


def _maybe_prune_profit_history() -> None:
    global _last_profit_history_prune_at

    prune_interval = int(os.getenv("PROFIT_HISTORY_PRUNE_INTERVAL_SECONDS", "3600"))
    if prune_interval <= 0:
        return

    now = time.time()
    if now - _last_profit_history_prune_at < prune_interval:
        return

    _prune_profit_history()
    _last_profit_history_prune_at = now


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
            _backfill_polymarket_position_metadata()
            conn = get_db_connection()
            try:
                cursor = conn.cursor()

                # Get all unique positions with symbol and market
                cursor.execute("""
                    SELECT DISTINCT symbol, market, token_id, outcome
                    FROM positions
                """)
                unique_positions = cursor.fetchall()
            finally:
                conn.close()

            print(f"[Price Update] Found {len(unique_positions)} positions to update")

            # Semaphore to control concurrency
            semaphore = asyncio.Semaphore(max_parallel)

            async def fetch_price(row):
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

                    if price is not None:
                        print(f"[Price Update] {symbol} ({market}, token={token_id or '-'}): ${price}")
                    else:
                        print(f"[Price Update] Failed to get price for {symbol} ({market}, token={token_id or '-'})")

                return {
                    "symbol": symbol,
                    "market": market,
                    "token_id": token_id,
                    "price": price,
                }

            # Fetch prices in parallel, then write them back in one short transaction.
            results = await asyncio.gather(*[fetch_price(row) for row in unique_positions])
            updates = [
                (item["price"], item["symbol"], item["market"], item["token_id"])
                for item in results
                if item["price"] is not None
            ]

            if updates:
                conn = get_db_connection()
                try:
                    cursor = conn.cursor()
                    cursor.executemany("""
                        UPDATE positions
                        SET current_price = ?
                        WHERE symbol = ? AND market = ? AND COALESCE(token_id, '') = COALESCE(?, '')
                    """, updates)
                    conn.commit()
                finally:
                    conn.close()

            # Update trending cache (no additional API call, uses same data)
            _update_trending_cache()

        except Exception as e:
            print(f"[Price Update Error] {e}")

        # Wait interval from environment variable (default: 5 minutes = 300 seconds)
        refresh_interval = int(os.getenv("POSITION_REFRESH_INTERVAL", "300"))
        print(f"[Price Update] Next update in {refresh_interval} seconds")
        await asyncio.sleep(refresh_interval)


async def refresh_market_news_snapshots_loop():
    """Background task to refresh market-news snapshots on a fixed interval."""
    from market_intel import refresh_market_news_snapshots

    refresh_interval = int(os.getenv("MARKET_NEWS_REFRESH_INTERVAL", "900"))

    # Give the API a moment to start before hitting external providers.
    await asyncio.sleep(3)

    while True:
        try:
            result = await asyncio.to_thread(refresh_market_news_snapshots)
            print(
                "[Market Intel] Refreshed market news snapshots: "
                f"inserted={result.get('inserted_categories', 0)} "
                f"errors={len(result.get('errors', {}))}"
            )
            for category, error in (result.get("errors") or {}).items():
                print(f"[Market Intel] {category} refresh failed: {error}")
        except Exception as e:
            print(f"[Market Intel Error] {e}")

        print(f"[Market Intel] Next market news refresh in {refresh_interval} seconds")
        await asyncio.sleep(refresh_interval)


async def refresh_macro_signal_snapshots_loop():
    """Background task to refresh macro signal snapshots on a fixed interval."""
    from market_intel import refresh_macro_signal_snapshot

    refresh_interval = int(os.getenv("MACRO_SIGNAL_REFRESH_INTERVAL", "900"))

    await asyncio.sleep(6)

    while True:
        try:
            result = await asyncio.to_thread(refresh_macro_signal_snapshot)
            print(
                "[Market Intel] Refreshed macro signal snapshot: "
                f"verdict={result.get('verdict')} "
                f"signals={result.get('total_count', 0)}"
            )
        except Exception as e:
            print(f"[Macro Signal Error] {e}")

        print(f"[Market Intel] Next macro signal refresh in {refresh_interval} seconds")
        await asyncio.sleep(refresh_interval)


async def refresh_etf_flow_snapshots_loop():
    """Background task to refresh ETF flow snapshots on a fixed interval."""
    from market_intel import refresh_etf_flow_snapshot

    refresh_interval = int(os.getenv("ETF_FLOW_REFRESH_INTERVAL", "900"))

    await asyncio.sleep(9)

    while True:
        try:
            result = await asyncio.to_thread(refresh_etf_flow_snapshot)
            print(
                "[Market Intel] Refreshed ETF flow snapshot: "
                f"direction={result.get('direction')} "
                f"tracked={result.get('tracked_count', 0)}"
            )
        except Exception as e:
            print(f"[ETF Flow Error] {e}")

        print(f"[Market Intel] Next ETF flow refresh in {refresh_interval} seconds")
        await asyncio.sleep(refresh_interval)


async def refresh_stock_analysis_snapshots_loop():
    """Background task to refresh featured stock-analysis snapshots."""
    from market_intel import refresh_stock_analysis_snapshots

    refresh_interval = int(os.getenv("STOCK_ANALYSIS_REFRESH_INTERVAL", "1800"))

    await asyncio.sleep(12)

    while True:
        try:
            result = await asyncio.to_thread(refresh_stock_analysis_snapshots)
            print(
                "[Market Intel] Refreshed stock analysis snapshots: "
                f"inserted={result.get('inserted_symbols', 0)} "
                f"errors={len(result.get('errors', {}))}"
            )
        except Exception as e:
            print(f"[Stock Analysis Error] {e}")

        print(f"[Market Intel] Next stock analysis refresh in {refresh_interval} seconds")
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

    print("[Profit History] Task starting...")

    while True:
        try:
            conn = get_db_connection()
            try:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT
                        a.id,
                        COALESCE(a.cash, 0) AS cash,
                        COALESCE(a.deposited, 0) AS deposited,
                        COALESCE(
                            SUM(
                                CASE
                                    WHEN p.current_price IS NULL THEN 0
                                    WHEN p.side = 'long' THEN p.current_price * ABS(p.quantity)
                                    ELSE p.entry_price * ABS(p.quantity)
                                END
                            ),
                            0
                        ) AS position_value
                    FROM agents a
                    LEFT JOIN positions p ON p.agent_id = a.id
                    GROUP BY a.id, a.cash, a.deposited
                """)
                agents = cursor.fetchall()
            finally:
                conn.close()

            print(f"[Profit History] Found {len(agents)} agents")

            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            rows_to_insert = []

            for agent in agents:
                agent_id = agent["id"]
                cash = agent["cash"] or 0
                deposited = agent["deposited"] or 0
                position_value = agent["position_value"] or 0
                initial_capital = 100000.0

                # Calculate profit: (cash + position) - (initial + deposited)
                # This excludes deposited cash from profit calculation
                total_value = cash + position_value
                profit = total_value - (initial_capital + deposited)
                # Clamp profit to avoid absurd values (e.g. from bad Polymarket price or API noise)
                _max_abs_profit = 1e12
                if abs(profit) > _max_abs_profit:
                    print(f"[Profit History] Agent {agent_id}: clamping absurd profit {profit} to ±{_max_abs_profit}")
                    profit = _max_abs_profit if profit > 0 else -_max_abs_profit
                rows_to_insert.append((agent_id, total_value, cash, position_value, profit, now))

            if rows_to_insert:
                conn = get_db_connection()
                try:
                    cursor = conn.cursor()
                    cursor.executemany("""
                        INSERT INTO profit_history (agent_id, total_value, cash, position_value, profit, recorded_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, rows_to_insert)
                    conn.commit()
                finally:
                    conn.close()
                _maybe_prune_profit_history()

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
            _backfill_polymarket_position_metadata()
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, agent_id, symbol, token_id, outcome, quantity, entry_price
                    FROM positions
                    WHERE market = 'polymarket'
                """)
                rows = cursor.fetchall()
            finally:
                conn.close()

            settled = 0
            skipped = 0
            cash_updates: dict[int, float] = {}
            settlement_rows: list[tuple[Any, ...]] = []
            delete_rows: list[tuple[int]] = []

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
                cash_updates[agent_id] = float(f"{cash_updates.get(agent_id, 0.0) + proceeds:.6f}")
                settlement_rows.append((
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
                delete_rows.append((pos_id,))
                settled += 1

            if settlement_rows:
                conn = get_db_connection()
                try:
                    cursor = conn.cursor()
                    cursor.executemany(
                        "UPDATE agents SET cash = cash + ? WHERE id = ?",
                        [(proceeds, agent_id) for agent_id, proceeds in cash_updates.items()],
                    )
                    cursor.executemany("""
                        INSERT INTO polymarket_settlements
                        (position_id, agent_id, symbol, token_id, outcome, quantity, entry_price, settlement_price, proceeds, market_slug, resolved_outcome, resolved_at, source_data)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, settlement_rows)
                    cursor.executemany("DELETE FROM positions WHERE id = ?", delete_rows)
                    conn.commit()
                finally:
                    conn.close()

            if settled > 0:
                print(f"[Polymarket Settler] settled={settled}, skipped={skipped}")

        except Exception as e:
            print(f"[Polymarket Settler Error] {e}")

        await asyncio.sleep(interval_s)
