"""三大法人買賣超 — institutional investor buy/sell flows.

TWSE OpenAPI's `BFI82U` (三大法人買賣超日報) is *not* in the official
swagger spec (verified 2026-05-12 via `https://openapi.twse.com.tw/v1/swagger.json`).
The actual data lives behind a `.csv`-returning legacy path that flips
shape monthly — fragile to depend on.

This module uses FinMind's free public dataset
`TaiwanStockInstitutionalInvestorsBuySell` as the primary source. It
covers TWSE-listed and TPEX-listed symbols, no auth required for light
use (rate-limited; set `FINMIND_API_TOKEN` for higher quota).

Returns *normalized* rows shaped like:

    {
        "date": "2026-05-08",
        "stock_id": "2330",
        "foreign_buy":  int,  # 外資 (含外資自營商)
        "foreign_sell": int,
        "investment_trust_buy":  int,  # 投信
        "investment_trust_sell": int,
        "dealer_buy":  int,  # 自營商 (自行買賣 + 避險合計)
        "dealer_sell": int,
        "net_total": int,   # 三大法人合計買賣超 = sum(buy - sell)
    }
"""

from __future__ import annotations

import os
from typing import Any, Optional

import requests

FINMIND_API_BASE = os.environ.get(
    "FINMIND_API_BASE", "https://api.finmindtrade.com/api/v4/data"
).rstrip("/")
FINMIND_TIMEOUT_SECONDS = float(os.environ.get("FINMIND_TIMEOUT_SECONDS", "10"))


def _aggregate_finmind_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse FinMind's per-investor-type rows into one row per (date, stock).

    FinMind returns one row per (date, stock, investor-name). We sum across
    investor names into the three canonical buckets the UI surfaces.
    """
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        date = str(row.get("date") or "").strip()
        stock_id = str(row.get("stock_id") or "").strip()
        if not date or not stock_id:
            continue
        name = str(row.get("name") or "").strip()
        buy = int(row.get("buy") or 0)
        sell = int(row.get("sell") or 0)

        key = (date, stock_id)
        agg = by_key.setdefault(
            key,
            {
                "date": date,
                "stock_id": stock_id,
                "foreign_buy": 0,
                "foreign_sell": 0,
                "investment_trust_buy": 0,
                "investment_trust_sell": 0,
                "dealer_buy": 0,
                "dealer_sell": 0,
            },
        )
        # FinMind investor-name buckets seen in the wild:
        #   Foreign_Investor, Foreign_Dealer_Self     -> foreign
        #   Investment_Trust                          -> investment trust
        #   Dealer_self, Dealer_Hedging               -> dealer
        if name.startswith("Foreign"):
            agg["foreign_buy"] += buy
            agg["foreign_sell"] += sell
        elif name == "Investment_Trust":
            agg["investment_trust_buy"] += buy
            agg["investment_trust_sell"] += sell
        elif name.startswith("Dealer"):
            agg["dealer_buy"] += buy
            agg["dealer_sell"] += sell

    out: list[dict[str, Any]] = []
    for agg in by_key.values():
        net = (
            agg["foreign_buy"] - agg["foreign_sell"]
            + agg["investment_trust_buy"] - agg["investment_trust_sell"]
            + agg["dealer_buy"] - agg["dealer_sell"]
        )
        agg["net_total"] = net
        out.append(agg)
    out.sort(key=lambda r: r["date"])
    return out


def fetch_institutional_flows(
    symbol: str,
    start_date: str,
    end_date: Optional[str] = None,
) -> Optional[list[dict[str, Any]]]:
    """Fetch normalized 三大法人 buy/sell rows for `symbol`.

    Args:
        symbol: TW stock ID like "2330".
        start_date: inclusive ISO date, e.g. "2026-05-01".
        end_date:   optional inclusive ISO date, defaults to today on the server.

    Returns the list of aggregated rows, or None on a network / shape error.
    Empty list is a *valid* answer (means: no trading day in range).
    """
    symbol_id = (symbol or "").strip().upper()
    if not symbol_id:
        return None
    params: dict[str, Any] = {
        "dataset": "TaiwanStockInstitutionalInvestorsBuySell",
        "data_id": symbol_id,
        "start_date": start_date,
    }
    if end_date:
        params["end_date"] = end_date
    token = os.environ.get("FINMIND_API_TOKEN")
    if token:
        params["token"] = token

    try:
        resp = requests.get(FINMIND_API_BASE, params=params, timeout=FINMIND_TIMEOUT_SECONDS)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as exc:
        print(f"[FinMind] institutional flows failed: {exc}")
        return None

    if not isinstance(payload, dict):
        return None
    if payload.get("status") != 200:
        print(f"[FinMind] non-success status: {payload.get('status')} msg={payload.get('msg')}")
        return None
    rows = payload.get("data") or []
    if not isinstance(rows, list):
        return None
    return _aggregate_finmind_rows(rows)


def get_latest_institutional_net(symbol: str) -> Optional[dict[str, Any]]:
    """Convenience: latest available aggregated row for `symbol`.

    Pulls the last 10 days then picks the latest aggregated row. Returns
    None if no data is available (e.g., non-trading week or bad symbol).
    """
    import datetime as _dt

    end = _dt.date.today()
    start = end - _dt.timedelta(days=10)
    rows = fetch_institutional_flows(symbol, start.isoformat(), end.isoformat())
    if not rows:
        return None
    return rows[-1]
