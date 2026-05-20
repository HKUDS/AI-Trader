#!/usr/bin/env python3
"""
Repair positions and signals that used deprecated market aliases such as "binance".

Usage:
  cd /home/AI-Trader/service/server
  python3 scripts/repair_market_alias_positions.py --dry-run
  python3 scripts/repair_market_alias_positions.py --apply
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from cache import delete, delete_pattern
from database import get_db_connection
from price_fetcher import get_price_from_market
from routes_shared import (
    AGENT_SIGNALS_CACHE_KEY_PREFIX,
    GROUPED_SIGNALS_CACHE_KEY_PREFIX,
    LEADERBOARD_CACHE_KEY_PREFIX,
    PRICE_CACHE_KEY_PREFIX,
    TRENDING_CACHE_KEY,
    MARKET_ALIASES,
    normalize_market,
)


BACKUP_DIR = SERVER_DIR / "data" / "repair_backups"
REPAIRABLE_MARKETS = {alias for alias, normalized in MARKET_ALIASES.items() if normalized in {"crypto", "us-stock"}}


@dataclass
class RepairPlan:
    old_market: str
    new_market: str
    position_count: int
    signal_count: int
    affected_agent_ids: list[int]
    symbols: list[str]
    price_updates: dict[str, float | None]


def now_z() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def row_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    return {key: row[key] for key in row.keys()}


def fetch_all(cursor: Any, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cursor.execute(query, params)
    return [row_dict(row) for row in cursor.fetchall()]


def to_finite_price(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed <= 0:
        return None
    return parsed


def load_alias_markets(cursor: Any) -> list[str]:
    rows = fetch_all(
        cursor,
        """
        SELECT market FROM positions
        UNION
        SELECT market FROM signals WHERE message_type = 'operation'
        """,
    )
    markets = sorted({str(row["market"] or "").strip().lower() for row in rows})
    return [market for market in markets if market in REPAIRABLE_MARKETS and normalize_market(market) != market]


def normalize_crypto_symbol(symbol: Any) -> str:
    normalized = str(symbol or "").strip().upper()
    for suffix in ("-PERP", "PERP", "-USD", "/USD", "USD", "USDT"):
        if normalized.endswith(suffix) and len(normalized) > len(suffix):
            normalized = normalized[: -len(suffix)]
            break
    return {
        "XBT": "BTC",
        "XXBT": "BTC",
        "XXBTZ": "BTC",
        "XETH": "ETH",
        "XETHZ": "ETH",
    }.get(normalized.strip(), normalized.strip())


def build_backup_payload(cursor: Any, markets: list[str]) -> dict[str, Any]:
    if not markets:
        return {"captured_at": now_z(), "markets": [], "positions": [], "signals": [], "profit_history": []}

    placeholders = ",".join("?" for _ in markets)
    positions = fetch_all(
        cursor,
        f"SELECT * FROM positions WHERE lower(market) IN ({placeholders}) ORDER BY agent_id, market, symbol, id",
        tuple(markets),
    )
    signals = fetch_all(
        cursor,
        f"""
        SELECT *
        FROM signals
        WHERE message_type = 'operation' AND lower(market) IN ({placeholders})
        ORDER BY agent_id, COALESCE(executed_at, created_at), id
        """,
        tuple(markets),
    )
    agent_ids = sorted({int(row["agent_id"]) for row in positions + signals if row.get("agent_id") is not None})
    profit_history: list[dict[str, Any]] = []
    if agent_ids:
        agent_placeholders = ",".join("?" for _ in agent_ids)
        profit_history = fetch_all(
            cursor,
            f"""
            SELECT *
            FROM profit_history
            WHERE agent_id IN ({agent_placeholders})
            ORDER BY agent_id, recorded_at, id
            """,
            tuple(agent_ids),
        )

    return {
        "captured_at": now_z(),
        "markets": markets,
        "affected_agent_ids": agent_ids,
        "positions": positions,
        "signals": signals,
        "profit_history": profit_history,
    }


def write_backup(payload: dict[str, Any]) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP_DIR / f"market_alias_repair_backup_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    backup_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return backup_path


def build_repair_plan(cursor: Any, markets: list[str], *, fetch_prices: bool = True) -> list[RepairPlan]:
    plans: list[RepairPlan] = []
    executed_at = now_z()
    for old_market in markets:
        new_market = normalize_market(old_market)
        positions = fetch_all(
            cursor,
            """
            SELECT id, agent_id, symbol
            FROM positions
            WHERE lower(market) = ?
            ORDER BY agent_id, symbol, id
            """,
            (old_market,),
        )
        signals = fetch_all(
            cursor,
            """
            SELECT id, agent_id, symbol
            FROM signals
            WHERE message_type = 'operation' AND lower(market) = ?
            ORDER BY agent_id, symbol, id
            """,
            (old_market,),
        )
        if new_market == "crypto":
            symbols = sorted({normalize_crypto_symbol(row["symbol"]) for row in positions if str(row["symbol"] or "").strip()})
        else:
            symbols = sorted({str(row["symbol"] or "").strip().upper() for row in positions if str(row["symbol"] or "").strip()})
        price_updates: dict[str, float | None] = {}
        for symbol in symbols:
            price_updates[symbol] = None
            if fetch_prices and new_market == "crypto":
                price_updates[symbol] = to_finite_price(get_price_from_market(symbol, executed_at, new_market))

        affected_agent_ids = sorted({int(row["agent_id"]) for row in positions + signals if row.get("agent_id") is not None})
        plans.append(
            RepairPlan(
                old_market=old_market,
                new_market=new_market,
                position_count=len(positions),
                signal_count=len(signals),
                affected_agent_ids=affected_agent_ids,
                symbols=symbols,
                price_updates=price_updates,
            )
        )
    return plans


def invalidate_caches() -> None:
    delete_pattern(f"{LEADERBOARD_CACHE_KEY_PREFIX}:*")
    delete_pattern(f"{GROUPED_SIGNALS_CACHE_KEY_PREFIX}:*")
    delete_pattern(f"{AGENT_SIGNALS_CACHE_KEY_PREFIX}:*")
    delete_pattern(f"{PRICE_CACHE_KEY_PREFIX}:*")
    delete(TRENDING_CACHE_KEY)


def apply_plan(cursor: Any, plans: list[RepairPlan], affected_agent_ids: list[int]) -> dict[str, Any]:
    for plan in plans:
        if plan.new_market == "crypto":
            position_rows = fetch_all(
                cursor,
                "SELECT id, symbol FROM positions WHERE lower(market) = ?",
                (plan.old_market,),
            )
            for row in position_rows:
                symbol = normalize_crypto_symbol(row["symbol"])
                cursor.execute(
                    "UPDATE positions SET market = ?, symbol = ?, current_price = ? WHERE id = ?",
                    (plan.new_market, symbol, plan.price_updates.get(symbol), row["id"]),
                )

            signal_rows = fetch_all(
                cursor,
                """
                SELECT id, symbol
                FROM signals
                WHERE message_type = 'operation' AND lower(market) = ?
                """,
                (plan.old_market,),
            )
            for row in signal_rows:
                cursor.execute(
                    "UPDATE signals SET market = ?, symbol = ? WHERE id = ?",
                    (plan.new_market, normalize_crypto_symbol(row["symbol"]), row["id"]),
                )
        else:
            cursor.execute(
                "UPDATE positions SET market = ?, symbol = upper(symbol) WHERE lower(market) = ?",
                (plan.new_market, plan.old_market),
            )
            cursor.execute(
                """
                UPDATE signals
                SET market = ?, symbol = upper(symbol)
                WHERE message_type = 'operation' AND lower(market) = ?
                """,
                (plan.new_market, plan.old_market),
            )

    if affected_agent_ids:
        placeholders = ",".join("?" for _ in affected_agent_ids)
        cursor.execute(f"DELETE FROM profit_history WHERE agent_id IN ({placeholders})", tuple(affected_agent_ids))

    return {
        "updated_markets": [asdict(plan) for plan in plans],
        "deleted_profit_history_agent_ids": affected_agent_ids,
    }


def repair(*, apply: bool, fetch_prices: bool) -> dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        markets = load_alias_markets(cursor)
        plans = build_repair_plan(cursor, markets, fetch_prices=fetch_prices)
        affected_agent_ids = sorted({agent_id for plan in plans for agent_id in plan.affected_agent_ids})
        backup_path = None

        if apply and markets:
            backup_payload = build_backup_payload(cursor, markets)
            backup_path = write_backup(backup_payload)
            result = apply_plan(cursor, plans, affected_agent_ids)
            conn.commit()
            invalidate_caches()
        else:
            result = {"updated_markets": [asdict(plan) for plan in plans], "deleted_profit_history_agent_ids": affected_agent_ids}

        return {
            "mode": "apply" if apply else "dry-run",
            "backup_path": str(backup_path) if backup_path else None,
            "alias_markets": markets,
            **result,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair deprecated market aliases in positions/signals.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Print planned changes without writing.")
    mode.add_argument("--apply", action="store_true", help="Apply changes and write a backup first.")
    parser.add_argument("--skip-price-fetch", action="store_true", help="Normalize markets without refreshing current prices.")
    args = parser.parse_args()

    result = repair(apply=args.apply, fetch_prices=not args.skip_price_fetch)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
