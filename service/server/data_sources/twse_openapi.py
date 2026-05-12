"""TWSE OpenAPI extras — endpoints beyond `STOCK_DAY_ALL`.

`STOCK_DAY_ALL` (latest-day OHLCV snapshot) is already consumed by
`service.server.tw_market`. This module covers the *other* useful free
endpoints from `https://openapi.twse.com.tw/v1/`:

    /exchangeReport/BWIBBU_ALL   per-stock PE / dividend yield / PB
    /opendata/t187ap03_L         listed company basic info
    /opendata/t187ap05_P         public-company monthly revenue
    /fund/MI_QFIIS_sort_20       foreign-investor top-20 holdings

Endpoint paths were verified against the live swagger spec
(`https://openapi.twse.com.tw/v1/swagger.json`) on 2026-05-12.
Endpoints that are *not* in the swagger — e.g. `BFI82U` (三大法人買賣超日報) —
have been deliberately omitted to avoid shipping a 404-path.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import requests

TWSE_API_BASE = os.environ.get(
    "TWSE_API_BASE", "https://openapi.twse.com.tw/v1"
).rstrip("/")
TWSE_TIMEOUT_SECONDS = float(os.environ.get("TWSE_TIMEOUT_SECONDS", "10"))


def _fetch_json(path: str) -> Optional[list[dict[str, Any]]]:
    """GET a TWSE OpenAPI path and return its JSON list payload, or None."""
    url = f"{TWSE_API_BASE}{path}"
    try:
        resp = requests.get(url, timeout=TWSE_TIMEOUT_SECONDS)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as exc:
        print(f"[TWSE-OpenAPI] {path} failed: {exc}")
        return None
    if not isinstance(payload, list):
        print(f"[TWSE-OpenAPI] {path} returned non-list: {type(payload).__name__}")
        return None
    return payload


def fetch_pe_ratios() -> Optional[list[dict[str, Any]]]:
    """上市個股日本益比、殖利率及股價淨值比 — full TWSE snapshot.

    Endpoint: `/exchangeReport/BWIBBU_ALL`. Each row contains `Code`, `Name`,
    `PEratio`, `DividendYield`, `PBratio`, `ReportDate`.
    """
    return _fetch_json("/exchangeReport/BWIBBU_ALL")


def fetch_listed_companies() -> Optional[list[dict[str, Any]]]:
    """上市公司基本資料.

    Endpoint: `/opendata/t187ap03_L`. Returns full TWSE company directory
    (industry, address, capital, etc.).
    """
    return _fetch_json("/opendata/t187ap03_L")


def fetch_monthly_revenue() -> Optional[list[dict[str, Any]]]:
    """公開發行公司每月營業收入彙總表.

    Endpoint: `/opendata/t187ap05_P`. One row per public company per month,
    with current-month revenue, YoY/MoM changes, and cumulative figures.
    """
    return _fetch_json("/opendata/t187ap05_P")


def fetch_foreign_top20_holdings() -> Optional[list[dict[str, Any]]]:
    """集中市場外資及陸資持股前 20 名彙總表.

    Endpoint: `/fund/MI_QFIIS_sort_20`. The top 20 names by foreign holding
    ratio, reset daily.
    """
    return _fetch_json("/fund/MI_QFIIS_sort_20")


def get_pe_for_symbol(symbol: str) -> Optional[dict[str, Any]]:
    """Look up a single stock's PE / yield / PB row from `BWIBBU_ALL`.

    Returns the raw row dict, or None on miss / network failure.
    Caller decides how to parse the string values (TWSE returns numerics
    as strings, sometimes blank).
    """
    rows = fetch_pe_ratios()
    if not rows:
        return None
    normalized = (symbol or "").strip().upper()
    for row in rows:
        if isinstance(row, dict) and str(row.get("Code", "")).strip().upper() == normalized:
            return row
    return None
