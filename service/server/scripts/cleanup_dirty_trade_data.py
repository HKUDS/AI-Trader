#!/usr/bin/env python3
"""
Targeted cleanup for known dirty trade data that inflated the leaderboard.

What this script does:
- backs up the affected agents, signals, positions, and profit history
- removes clearly invalid operation signals
- rebuilds cash and positions for affected agents from the remaining operation history
- deletes stale profit_history rows for affected agents so charts can repopulate cleanly
- clears Redis-backed leaderboard/signal caches when available

Usage:
  cd /home/AI-Trader/service/server
  python3 scripts/cleanup_dirty_trade_data.py --dry-run
  python3 scripts/cleanup_dirty_trade_data.py --apply
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from cache import delete, delete_pattern
from database import get_db_connection
from fees import TRADE_FEE_RATE
from routes_shared import (
    AGENT_SIGNALS_CACHE_KEY_PREFIX,
    GROUPED_SIGNALS_CACHE_KEY_PREFIX,
    LEADERBOARD_CACHE_KEY_PREFIX,
    TRENDING_CACHE_KEY,
)


INITIAL_CAPITAL = 100000.0
EPSILON = 1e-9
BACKUP_DIR = SERVER_DIR / "data" / "repair_backups"
US_STOCK_PLACEHOLDER_SYMBOLS = {"PORTFOLIO", "STRATEGY"}


def normalized_market(value: Any) -> str:
    return str(value or "").strip().lower()


def normalized_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


@dataclass
class PositionState:
    symbol: str
    market: str
    token_id: str | None
    outcome: str | None
    side: str
    quantity: float
    entry_price: float
    current_price: float | None
    opened_at: str
    leader_id: int | None


def now_z() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
        if not math.isfinite(parsed):
            return default
        return parsed
    except (TypeError, ValueError):
        return default


def row_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    return {key: row[key] for key in row.keys()}


def instrument_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    market = str(row.get("market") or "")
    if market == "polymarket":
        return (
            market,
            str(row.get("token_id") or row.get("symbol") or ""),
            str(row.get("outcome") or ""),
            str(row.get("symbol") or ""),
        )
    return (
        market,
        str(row.get("symbol") or ""),
        "",
        "",
    )


def suspicious_reasons(signal: dict[str, Any]) -> list[str]:
    market = normalized_market(signal.get("market"))
    symbol = normalized_symbol(signal.get("symbol"))
    entry_price = to_float(signal.get("entry_price"))
    quantity = abs(to_float(signal.get("quantity")))
    position_current_price = to_float(signal.get("position_current_price"), default=0.0)

    reasons: list[str] = []
    if market == "polymarket" and entry_price > 1.0 + EPSILON:
        reasons.append("polymarket_price_gt_1")
    if market == "crypto" and symbol in {"AAPL", "TSLA"}:
        reasons.append("stock_symbol_in_crypto_market")
    if market == "crypto" and symbol in {"BTC", "BTCUSDT"} and entry_price < 1000.0 - EPSILON:
        reasons.append("btc_price_too_low")
    if market == "crypto" and symbol in {"ETH", "ETHUSDT"} and entry_price < 100.0 - EPSILON:
        reasons.append("eth_price_too_low")
    if market == "crypto" and symbol in {"BNB", "BNBUSDT"} and entry_price < 10.0 - EPSILON:
        reasons.append("bnb_price_too_low")
    if market == "crypto" and symbol in {"SOL", "SOLUSDT"} and entry_price < 10.0 - EPSILON:
        reasons.append("sol_price_too_low")
    if market == "crypto" and symbol == "HYPE" and entry_price < 10.0 - EPSILON:
        reasons.append("hype_price_too_low")
    if market == "crypto" and symbol in {"PAXG", "PAXGUSD"} and entry_price < 1000.0 - EPSILON:
        reasons.append("paxg_price_too_low")
    if (
        market == "us-stock"
        and symbol not in US_STOCK_PLACEHOLDER_SYMBOLS
        and entry_price > EPSILON
        and position_current_price > EPSILON
        and position_current_price / entry_price >= 20.0
        and abs(position_current_price - entry_price) * quantity >= 5000.0
    ):
        reasons.append("us_stock_entry_price_outlier")
    return reasons


def fetch_all(cursor: Any, query: str, params: Iterable[Any] | None = None) -> list[dict[str, Any]]:
    cursor.execute(query, params or ())
    return [row_dict(row) for row in cursor.fetchall()]


def load_suspicious_operation_signals(cursor: Any) -> list[dict[str, Any]]:
    rows = fetch_all(
        cursor,
        """
        WITH position_price_refs AS (
            SELECT
                agent_id,
                LOWER(market) AS market_key,
                UPPER(symbol) AS symbol_key,
                COALESCE(token_id, '') AS token_key,
                MAX(current_price) AS current_price
            FROM positions
            WHERE current_price IS NOT NULL
            GROUP BY agent_id, LOWER(market), UPPER(symbol), COALESCE(token_id, '')
        )
        SELECT
            s.*,
            a.name AS agent_name,
            ppr.current_price AS position_current_price
        FROM signals s
        JOIN agents a ON a.id = s.agent_id
        LEFT JOIN position_price_refs ppr
          ON ppr.agent_id = s.agent_id
         AND ppr.market_key = LOWER(s.market)
         AND ppr.symbol_key = UPPER(s.symbol)
         AND ppr.token_key = COALESCE(s.token_id, '')
        WHERE s.message_type = 'operation'
          AND (
            (LOWER(s.market) = 'polymarket' AND s.entry_price > 1.0)
            OR (LOWER(s.market) = 'crypto' AND UPPER(s.symbol) IN ('AAPL', 'TSLA'))
            OR (LOWER(s.market) = 'crypto' AND UPPER(s.symbol) IN ('BTC', 'BTCUSDT') AND s.entry_price < 1000.0)
            OR (LOWER(s.market) = 'crypto' AND UPPER(s.symbol) IN ('ETH', 'ETHUSDT') AND s.entry_price < 100.0)
            OR (LOWER(s.market) = 'crypto' AND UPPER(s.symbol) IN ('BNB', 'BNBUSDT') AND s.entry_price < 10.0)
            OR (LOWER(s.market) = 'crypto' AND UPPER(s.symbol) IN ('SOL', 'SOLUSDT') AND s.entry_price < 10.0)
            OR (LOWER(s.market) = 'crypto' AND UPPER(s.symbol) = 'HYPE' AND s.entry_price < 10.0)
            OR (LOWER(s.market) = 'crypto' AND UPPER(s.symbol) IN ('PAXG', 'PAXGUSD') AND s.entry_price < 1000.0)
            OR (
                LOWER(s.market) = 'us-stock'
                AND UPPER(s.symbol) NOT IN ('PORTFOLIO', 'STRATEGY')
                AND s.entry_price > 0
                AND ppr.current_price IS NOT NULL
                AND ppr.current_price / s.entry_price >= 20.0
                AND ABS(ppr.current_price - s.entry_price) * COALESCE(s.quantity, 0) >= 5000.0
            )
          )
        ORDER BY a.name, COALESCE(s.executed_at, s.created_at), s.id
        """,
    )
    for row in rows:
        row["suspicious_reasons"] = suspicious_reasons(row)
    return rows


def filter_suspicious_rows(
    rows: list[dict[str, Any]],
    target_agent_ids: set[int] | None,
) -> list[dict[str, Any]]:
    if not target_agent_ids:
        return rows
    return [row for row in rows if int(row["agent_id"]) in target_agent_ids]


def load_agent_rows(cursor: Any, agent_ids: list[int]) -> list[dict[str, Any]]:
    placeholders = ",".join("?" for _ in agent_ids)
    return fetch_all(
        cursor,
        f"SELECT * FROM agents WHERE id IN ({placeholders}) ORDER BY id",
        agent_ids,
    )


def load_agent_positions(cursor: Any, agent_ids: list[int]) -> list[dict[str, Any]]:
    placeholders = ",".join("?" for _ in agent_ids)
    return fetch_all(
        cursor,
        f"""
        SELECT *
        FROM positions
        WHERE agent_id IN ({placeholders})
        ORDER BY agent_id, market, symbol, token_id
        """,
        agent_ids,
    )


def load_agent_signals(cursor: Any, agent_ids: list[int]) -> list[dict[str, Any]]:
    placeholders = ",".join("?" for _ in agent_ids)
    return fetch_all(
        cursor,
        f"""
        SELECT *
        FROM signals
        WHERE agent_id IN ({placeholders})
        ORDER BY agent_id, COALESCE(executed_at, created_at), id
        """,
        agent_ids,
    )


def load_agent_profit_history(cursor: Any, agent_ids: list[int]) -> list[dict[str, Any]]:
    placeholders = ",".join("?" for _ in agent_ids)
    return fetch_all(
        cursor,
        f"""
        SELECT *
        FROM profit_history
        WHERE agent_id IN ({placeholders})
        ORDER BY agent_id, recorded_at, id
        """,
        agent_ids,
    )


def build_backup_payload(cursor: Any, suspicious_rows: list[dict[str, Any]]) -> dict[str, Any]:
    agent_ids = sorted({int(row["agent_id"]) for row in suspicious_rows})
    return {
        "captured_at": now_z(),
        "affected_agent_ids": agent_ids,
        "suspicious_operation_signals": suspicious_rows,
        "agents": load_agent_rows(cursor, agent_ids),
        "positions": load_agent_positions(cursor, agent_ids),
        "signals": load_agent_signals(cursor, agent_ids),
        "profit_history": load_agent_profit_history(cursor, agent_ids),
    }


def write_backup(payload: dict[str, Any]) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP_DIR / f"dirty_trade_cleanup_backup_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    backup_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return backup_path


def previous_position_index(rows: list[dict[str, Any]]) -> dict[int, dict[tuple[str, str, str, str], dict[str, Any]]]:
    indexed: dict[int, dict[tuple[str, str, str, str], dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        indexed[int(row["agent_id"])][instrument_key(row)] = row
    return indexed


def create_position_from_signal(signal: dict[str, Any], quantity: float, side: str) -> PositionState:
    return PositionState(
        symbol=str(signal.get("symbol") or ""),
        market=str(signal.get("market") or ""),
        token_id=(str(signal.get("token_id")) if signal.get("token_id") is not None else None),
        outcome=(str(signal.get("outcome")) if signal.get("outcome") is not None else None),
        side=side,
        quantity=quantity,
        entry_price=to_float(signal.get("entry_price")),
        current_price=None,
        opened_at=str(signal.get("executed_at") or signal.get("created_at") or now_z()),
        leader_id=None,
    )


def replay_agent_operations(
    agent: dict[str, Any],
    operation_rows: list[dict[str, Any]],
    suspicious_ids: set[int],
    previous_positions_by_key: dict[tuple[str, str, str, str], dict[str, Any]],
) -> tuple[float, list[PositionState], list[dict[str, Any]]]:
    cash = INITIAL_CAPITAL + to_float(agent.get("deposited"))
    positions: dict[tuple[str, str, str, str], PositionState] = {}
    skipped_rows: list[dict[str, Any]] = []

    for row in operation_rows:
        if int(row["id"]) in suspicious_ids:
            continue

        action = str(row.get("side") or "").lower()
        qty = to_float(row.get("quantity"))
        price = to_float(row.get("entry_price"))
        executed_at = str(row.get("executed_at") or row.get("created_at") or now_z())

        if action not in {"buy", "sell", "short", "cover"} or qty <= EPSILON or price <= EPSILON:
            skipped_rows.append({"id": int(row["id"]), "reason": "invalid_signal_payload"})
            continue

        key = instrument_key(row)
        pos = positions.get(key)
        trade_value = price * qty
        fee = trade_value * TRADE_FEE_RATE

        try:
            if action == "buy":
                if pos and pos.quantity < -EPSILON:
                    raise ValueError("buy_with_open_short")
                total_cost = trade_value + fee
                if cash + EPSILON < total_cost:
                    raise ValueError("insufficient_cash_for_buy")
                cash -= total_cost
                if pos and pos.quantity > EPSILON:
                    new_qty = pos.quantity + qty
                    pos.entry_price = ((pos.quantity * pos.entry_price) + (qty * price)) / new_qty
                    pos.quantity = new_qty
                    pos.opened_at = executed_at
                else:
                    positions[key] = create_position_from_signal(row, qty, "long")

            elif action == "sell":
                if not pos or pos.quantity <= EPSILON:
                    raise ValueError("sell_without_long")
                if qty > pos.quantity + EPSILON:
                    raise ValueError("sell_exceeds_long_quantity")
                cash += trade_value - fee
                pos.quantity -= qty
                if pos.quantity <= EPSILON:
                    positions.pop(key, None)

            elif action == "short":
                if str(row.get("market") or "") == "polymarket":
                    raise ValueError("polymarket_short_not_supported")
                if pos and pos.quantity > EPSILON:
                    raise ValueError("short_with_open_long")
                total_cost = trade_value + fee
                if cash + EPSILON < total_cost:
                    raise ValueError("insufficient_cash_for_short")
                cash -= total_cost
                if pos and pos.quantity < -EPSILON:
                    current_abs = abs(pos.quantity)
                    new_abs = current_abs + qty
                    pos.entry_price = ((current_abs * pos.entry_price) + (qty * price)) / new_abs
                    pos.quantity = -new_abs
                    pos.opened_at = executed_at
                else:
                    positions[key] = create_position_from_signal(row, -qty, "short")

            elif action == "cover":
                if not pos or pos.quantity >= -EPSILON:
                    raise ValueError("cover_without_short")
                if qty > abs(pos.quantity) + EPSILON:
                    raise ValueError("cover_exceeds_short_quantity")
                cash += ((2 * pos.entry_price) - price) * qty - fee
                pos.quantity += qty
                if pos.quantity >= -EPSILON:
                    positions.pop(key, None)

        except ValueError as exc:
            skipped_rows.append({"id": int(row["id"]), "reason": str(exc)})
            continue

    rebuilt_positions: list[PositionState] = []
    for key, pos in positions.items():
        previous = previous_positions_by_key.get(key)
        if previous:
            pos.current_price = previous.get("current_price")
            pos.leader_id = previous.get("leader_id")
        rebuilt_positions.append(pos)

    return cash, rebuilt_positions, skipped_rows


def invalidate_caches() -> None:
    delete_pattern(f"{LEADERBOARD_CACHE_KEY_PREFIX}:*")
    delete_pattern(f"{GROUPED_SIGNALS_CACHE_KEY_PREFIX}:*")
    delete_pattern(f"{AGENT_SIGNALS_CACHE_KEY_PREFIX}:*")
    delete(TRENDING_CACHE_KEY)


def apply_cleanup(target_agent_ids: set[int] | None = None) -> dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()

    suspicious_rows = filter_suspicious_rows(load_suspicious_operation_signals(cursor), target_agent_ids)
    if not suspicious_rows:
        conn.close()
        return {
            "backup_path": None,
            "affected_agents": [],
            "deleted_signal_ids": [],
            "skipped_rows": {},
            "message": "No suspicious operation signals found.",
        }

    backup_payload = build_backup_payload(cursor, suspicious_rows)
    backup_path = write_backup(backup_payload)

    agent_rows = {int(row["id"]): row for row in backup_payload["agents"]}
    previous_positions = previous_position_index(backup_payload["positions"])
    signals_by_agent: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in backup_payload["signals"]:
        if row.get("message_type") == "operation":
            signals_by_agent[int(row["agent_id"])].append(row)

    suspicious_ids = {int(row["id"]) for row in suspicious_rows}
    suspicious_ids_by_agent: dict[int, set[int]] = defaultdict(set)
    for row in suspicious_rows:
        suspicious_ids_by_agent[int(row["agent_id"])].add(int(row["id"]))

    rebuilt_agents: list[dict[str, Any]] = []
    deleted_row_ids: set[int] = set(suspicious_ids)
    skipped_rows_by_agent: dict[int, list[dict[str, Any]]] = {}

    for agent_id in sorted(agent_rows):
        new_cash, new_positions, skipped_rows = replay_agent_operations(
            agent_rows[agent_id],
            signals_by_agent.get(agent_id, []),
            suspicious_ids_by_agent.get(agent_id, set()),
            previous_positions.get(agent_id, {}),
        )
        skipped_rows_by_agent[agent_id] = skipped_rows
        deleted_row_ids.update(int(item["id"]) for item in skipped_rows)
        rebuilt_agents.append(
            {
                "agent_id": agent_id,
                "agent_name": agent_rows[agent_id]["name"],
                "old_cash": to_float(agent_rows[agent_id].get("cash")),
                "new_cash": new_cash,
                "rebuilt_positions": [pos.__dict__ for pos in new_positions],
                "deleted_signal_count": len(suspicious_ids_by_agent.get(agent_id, set())) + len(skipped_rows),
            }
        )

    affected_agent_ids = [int(row["id"]) for row in backup_payload["agents"]]

    try:
        if deleted_row_ids:
            deleted_rows = [
                row for row in backup_payload["signals"]
                if int(row["id"]) in deleted_row_ids
            ]
            deleted_public_signal_ids = sorted({
                int(row["signal_id"])
                for row in deleted_rows
                if row.get("signal_id") is not None
            })
            row_placeholders = ",".join("?" for _ in deleted_row_ids)
            if deleted_public_signal_ids:
                signal_placeholders = ",".join("?" for _ in deleted_public_signal_ids)
                cursor.execute(
                    f"DELETE FROM signal_replies WHERE signal_id IN ({signal_placeholders})",
                    deleted_public_signal_ids,
                )
            cursor.execute(
                f"DELETE FROM signals WHERE id IN ({row_placeholders})",
                list(deleted_row_ids),
            )

        placeholders = ",".join("?" for _ in affected_agent_ids)
        cursor.execute(f"DELETE FROM positions WHERE agent_id IN ({placeholders})", affected_agent_ids)
        cursor.execute(f"DELETE FROM profit_history WHERE agent_id IN ({placeholders})", affected_agent_ids)

        for item in rebuilt_agents:
            cursor.execute(
                "UPDATE agents SET cash = ? WHERE id = ?",
                (item["new_cash"], item["agent_id"]),
            )
            for pos in item["rebuilt_positions"]:
                cursor.execute(
                    """
                    INSERT INTO positions (
                        agent_id, leader_id, symbol, market, token_id, outcome,
                        side, quantity, entry_price, current_price, opened_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item["agent_id"],
                        pos["leader_id"],
                        pos["symbol"],
                        pos["market"],
                        pos["token_id"],
                        pos["outcome"],
                        pos["side"],
                        pos["quantity"],
                        pos["entry_price"],
                        pos["current_price"],
                        pos["opened_at"],
                    ),
                )

        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise

    conn.close()
    invalidate_caches()

    return {
        "backup_path": str(backup_path),
        "affected_agents": rebuilt_agents,
        "deleted_signal_ids": sorted(deleted_row_ids),
        "skipped_rows": skipped_rows_by_agent,
        "message": "Cleanup applied successfully.",
    }


def dry_run(target_agent_ids: set[int] | None = None) -> dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    suspicious_rows = filter_suspicious_rows(load_suspicious_operation_signals(cursor), target_agent_ids)
    conn.close()

    summary_by_agent: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "reasons": defaultdict(int)})
    for row in suspicious_rows:
        bucket = summary_by_agent[str(row["agent_name"])]
        bucket["count"] += 1
        for reason in row["suspicious_reasons"]:
            bucket["reasons"][reason] += 1

    return {
        "captured_at": now_z(),
        "suspicious_signal_count": len(suspicious_rows),
        "agents": {
            name: {
                "count": item["count"],
                "reasons": dict(item["reasons"]),
            }
            for name, item in summary_by_agent.items()
        },
        "signals": suspicious_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean up known dirty trade data.")
    parser.add_argument("--apply", action="store_true", help="apply the cleanup")
    parser.add_argument("--dry-run", action="store_true", help="show what would be cleaned")
    parser.add_argument(
        "--agent-id",
        action="append",
        type=int,
        default=[],
        help="limit cleanup to one agent id; can be passed multiple times",
    )
    args = parser.parse_args()

    if args.apply and args.dry_run:
        parser.error("choose either --apply or --dry-run, not both")

    target_agent_ids = set(args.agent_id) if args.agent_id else None

    if not args.apply:
        report = dry_run(target_agent_ids)
        print(json.dumps(report, indent=2, default=str))
        return 0

    result = apply_cleanup(target_agent_ids)
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
