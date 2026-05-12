# BW-Trader · fork `as84089443/AI-Trader` main audit
**Date:** 2026-05-12
**HEAD:** `5a90b81` (PR #2 merged) — "feat: auto-research + paper trading NT$1M (Phase 2 + 4 + last30days + TW scheduler/news)"
**Audit scope:** verify which files claimed in PR #1 / PR #2 actually exist on `main`, separate truth from inflation, identify real gaps.

---

## TL;DR

A previous Claude session reported **"on fork main `f84d79c`, `pionex_client.py` / `tw_market.py` do not exist; the marathon self-reported 'done' but nothing landed."** That claim is **partially false**.

**Truth:**

- `pionex_client.py` — **really does not exist** ✅ (matches that earlier claim)
- `tw_market.py`, `finmind_client.py`, `paper_engine.py`, `scheduler.py`, `security/no_auto_trade.py`, `news/tw_news.py`, `research/last30days_client.py` — **all really exist** on `5a90b81`. The earlier audit was wrong about these.
- `brokers/` directory — **does not exist** ✅
- `data/` directory — **does not exist** ✅
- TWSE OpenAPI is wired into `price_fetcher.py:598-606` (TW path) and works. FinMind fallback is also wired.
- **No `twstock` usage anywhere** — confirmed via `pip` / requirements grep. No realtime quotes, no 四大買賣點, no built-in MA/BIAS analytics.

So the earlier audit *overstated* the gap. The actual remaining gap (what PR #2 did not deliver) is:

1. No broker client of any kind (Pionex, Binance, IB, etc.).
2. No realtime quote source — TW path is daily-close only via TWSE OpenAPI snapshot.
3. No use of `twstock` library (1.5k★, TWSE+TPEX coverage, built-in analytics).
4. No coverage of TWSE OpenAPI beyond `STOCK_DAY_ALL` — no PE/殖利率/月營收/外資持股endpoints.

This PR closes that real gap.

---

## File-by-file truth table

### Files claimed (explicitly or implicitly) by PR #1 / PR #2

| File | Claim | Actual on `5a90b81` | Note |
|---|---|---|---|
| `service/server/tw_market.py` | exists | **EXISTS** (4186 B) | TWSE OpenAPI `STOCK_DAY_ALL` daily-close lookup. Works. |
| `service/server/finmind_client.py` | exists | **EXISTS** (3308 B) | FinMind `TaiwanStockPrice` 14-day window fallback. Works. |
| `service/server/paper_engine.py` | exists | **EXISTS** (10677 B) | Paper trading engine. |
| `service/server/scheduler.py` | exists | **EXISTS** (8497 B) | TW market scheduler. |
| `service/server/security/no_auto_trade.py` | exists | **EXISTS** (6029 B) | "No auto-trade" guard. |
| `service/server/news/tw_news.py` | exists | **EXISTS** (8528 B) | TW news fetcher. |
| `service/server/research/last30days_client.py` | exists | **EXISTS** (8140 B) | last30days research client. |
| `service/server/tests/test_tw_market.py` | exists | **EXISTS** | Unit tests for `tw_market.py`. |
| `service/server/tests/test_no_auto_trade.py` | exists | **EXISTS** | |
| `service/server/tests/test_paper_engine.py` | exists | **EXISTS** | |
| `service/server/tests/test_research.py` | exists | **EXISTS** | |
| `service/server/tests/test_scheduler.py` | exists | **EXISTS** | |
| `service/server/tests/test_tw_news.py` | exists | **EXISTS** | |

### Files the earlier audit said were "missing" but actually exist

Every file in the previous table — the earlier audit was incorrect, *or* was looking at a different commit (perhaps `f84d79c` referred to a stale snapshot prior to PR #2 being merged on 2026-05-11). **As of `5a90b81` (current `main`), all the PR-#2 work is on disk and importable.**

### Genuinely missing (what we need to add)

| Path | Status | Why we want it |
|---|---|---|
| `service/server/brokers/` | **missing** (no directory) | broker abstraction layer doesn't exist yet |
| `service/server/brokers/pionex_client.py` | **missing** | crypto broker for Phase-3 copytrade |
| `service/server/data_sources/` | **missing** (no directory) | data-source layer separate from primary `price_fetcher`. Note: `/service/server/data/` is in `.gitignore` line 128 (likely reserved for runtime dumps) so the code layer goes under `data_sources/` instead. |
| `service/server/data_sources/tw_market_twstock.py` | **missing** | realtime quotes + historical OHLCV + 四大買賣點 via `mlouielu/twstock` |
| `service/server/data_sources/twse_openapi.py` | **missing** | extra TWSE OpenAPI endpoints beyond `STOCK_DAY_ALL` (PE/月營收/外資持股) |
| `twstock>=1.5.0` in `requirements.txt` | **missing** | dependency for above |

---

## Existing TW data path (already wired)

`service/server/price_fetcher.py:598-606`:

```python
elif market == "tw-stock":
    # BW-Trader TW path: TWSE OpenAPI for latest daily close,
    # FinMind as historical fallback.
    from tw_market import get_tw_stock_price
    from finmind_client import get_tw_stock_price_finmind
    price = get_tw_stock_price(symbol, executed_at)
    if price is None:
        price = get_tw_stock_price_finmind(symbol, executed_at)
```

**Gap:** daily close only — no intraday / realtime. The PR-#2 roadmap explicitly called out realtime as Phase 2 work that wasn't yet done. `twstock.realtime.get(symbol)` closes that gap.

---

## TWSE OpenAPI swagger discovery (real endpoints only)

Pulled `https://openapi.twse.com.tw/v1/swagger.json` (HTTP 200, 306 KB). 143 paths total. Confirmed endpoints we will use:

| Path | Summary (Mandarin) | Use case |
|---|---|---|
| `/exchangeReport/STOCK_DAY_ALL` | 上市個股日成交資訊 | already used by `tw_market.py` |
| `/exchangeReport/BWIBBU_ALL` | 上市個股日本益比、殖利率及股價淨值比 | per-stock PE / yield / PB |
| `/opendata/t187ap03_L` | 上市公司基本資料 | company metadata |
| `/opendata/t187ap05_P` | 公開發行公司每月營業收入彙總表 | monthly revenue |
| `/fund/MI_QFIIS_sort_20` | 集中市場外資及陸資持股前 20 名彙總表 | foreign holdings top-20 |

**Endpoint `BFI82U`** ("三大法人買賣超日報", mentioned in the original task prompt) — **does not exist** in the TWSE OpenAPI v1 swagger. The only `BFI*` paths are `BFI61U` (公債補息), `BFI84U` (停資停券), `BFIAUU_d/m/y` (鉅額交易). Not writing it.

---

## twstock 1.5.1 API surface (verified via local install)

`uv pip install twstock` → 1.5.1 installs cleanly. Confirmed surface:

```python
twstock.codes  # dict[str, StockCodeInfo]
# StockCodeInfo(type, code, name, ISIN, start, market, group, CFI, data_source)

twstock.Stock(sid, initial_fetch=True, force_data_source=None)
# methods: fetch, fetch_31, fetch_from(year, month), moving_average, ma_bias_ratio
# attrs:   date, capacity, turnover, open, high, low, close, change, transaction, price

twstock.realtime.get(symbol) -> dict
# returns {'success': bool, 'info': {...}, 'realtime': {...}, 'timestamp': float}

twstock.BestFourPoint(stock).best_four_point_to_buy()  -> tuple | False
twstock.BestFourPoint(stock).best_four_point_to_sell() -> tuple | False
twstock.BestFourPoint(stock).best_four_point()         -> tuple | False
```

DATATUPLE from `twstock.stock.DATATUPLE._fields`:
`('date', 'capacity', 'turnover', 'open', 'high', 'low', 'close', 'change', 'transaction', 'note')`

**Gotcha:** `Stock(sid)` default `initial_fetch=True` hits the network in `__init__`. For metadata-only paths we pass `initial_fetch=False`.

---

## Action plan (delivered in this branch `feat/real-tw-data-layer`)

1. `service/server/data_sources/tw_market_twstock.py` — twstock wrapper (metadata, historical, realtime, 四大買賣點) with 3-req/5s throttle.
2. `service/server/data_sources/twse_openapi.py` — confirmed TWSE OpenAPI endpoints (PE/月營收/外資持股 + company basic info). No hallucinated paths.
3. `service/server/brokers/pionex_client.py` — read-only Pionex client (balance + klines), HMAC-SHA256 signing, no trading endpoints.
4. `service/server/price_fetcher.py` wiring — TW path tries twstock realtime first, then existing `tw_market.py` daily, then FinMind. Backward compatible: if `twstock` import fails the existing path is used unchanged.
5. Tests in `service/server/tests/` matching existing convention (top-level imports, `SERVER_DIR` on sys.path, `unittest.mock`).
6. `service/requirements.txt`: add `twstock>=1.5.0`.

Every file is verified to import in a clean `python -c "import ..."` smoke before commit.
