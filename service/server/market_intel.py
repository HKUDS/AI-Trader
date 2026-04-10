"""
Market intelligence snapshots and read models.

第一阶段先实现统一的金融新闻聚合快照：
- 后台统一从 Alpha Vantage NEWS_SENTIMENT 拉取
- 存入本地快照表
- 前端和 API 只读消费快照
"""

from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
import re

import requests
try:
    from openrouter import OpenRouter
except ImportError:  # pragma: no cover - optional dependency in some environments
    OpenRouter = None

from cache import delete_pattern, get_json, set_json
from config import ALPHA_VANTAGE_API_KEY
from database import get_db_connection

ALPHA_VANTAGE_BASE_URL = os.getenv("ALPHA_VANTAGE_BASE_URL", "https://www.alphavantage.co/query").strip()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "").strip()
MARKET_NEWS_LOOKBACK_HOURS = int(os.getenv("MARKET_NEWS_LOOKBACK_HOURS", "48"))
MARKET_NEWS_CATEGORY_LIMIT = int(os.getenv("MARKET_NEWS_CATEGORY_LIMIT", "12"))
MARKET_NEWS_HISTORY_PER_CATEGORY = int(os.getenv("MARKET_NEWS_HISTORY_PER_CATEGORY", "96"))
MACRO_SIGNAL_HISTORY_LIMIT = int(os.getenv("MACRO_SIGNAL_HISTORY_LIMIT", "96"))
MACRO_SIGNAL_LOOKBACK_DAYS = int(os.getenv("MACRO_SIGNAL_LOOKBACK_DAYS", "20"))
BTC_MACRO_LOOKBACK_DAYS = int(os.getenv("BTC_MACRO_LOOKBACK_DAYS", "7"))
ETF_FLOW_HISTORY_LIMIT = int(os.getenv("ETF_FLOW_HISTORY_LIMIT", "96"))
ETF_FLOW_LOOKBACK_DAYS = int(os.getenv("ETF_FLOW_LOOKBACK_DAYS", "1"))
ETF_FLOW_BASELINE_VOLUME_DAYS = int(os.getenv("ETF_FLOW_BASELINE_VOLUME_DAYS", "5"))
STOCK_ANALYSIS_HISTORY_LIMIT = int(os.getenv("STOCK_ANALYSIS_HISTORY_LIMIT", "120"))
MARKET_NEWS_CACHE_TTL_SECONDS = max(30, int(os.getenv("MARKET_NEWS_REFRESH_INTERVAL", "3600")))
MACRO_SIGNAL_CACHE_TTL_SECONDS = max(30, int(os.getenv("MACRO_SIGNAL_REFRESH_INTERVAL", "3600")))
ETF_FLOW_CACHE_TTL_SECONDS = max(30, int(os.getenv("ETF_FLOW_REFRESH_INTERVAL", "3600")))
STOCK_ANALYSIS_CACHE_TTL_SECONDS = max(30, int(os.getenv("STOCK_ANALYSIS_REFRESH_INTERVAL", "7200")))
MARKET_INTEL_OVERVIEW_CACHE_TTL_SECONDS = max(
    30,
    min(
        MARKET_NEWS_CACHE_TTL_SECONDS,
        MACRO_SIGNAL_CACHE_TTL_SECONDS,
        ETF_FLOW_CACHE_TTL_SECONDS,
        STOCK_ANALYSIS_CACHE_TTL_SECONDS,
    ),
)
FALLBACK_STOCK_ANALYSIS_SYMBOLS = [
    symbol.strip().upper()
    for symbol in os.getenv("MARKET_INTEL_STOCK_SYMBOLS", "NVDA,AAPL,MSFT,AMZN,TSLA,META").split(",")
    if symbol.strip()
]

NEWS_CATEGORY_DEFINITIONS: dict[str, dict[str, str]] = {
    "equities": {
        "label": "Equities",
        "label_zh": "股票",
        "description": "Stocks, ETFs, and company market developments.",
        "description_zh": "股票、ETF 与公司市场动态。",
        "topics": "financial_markets",
    },
    "macro": {
        "label": "Macro",
        "label_zh": "宏观",
        "description": "Macro regime, policy, and broad economic context.",
        "description_zh": "宏观环境、政策与整体经济背景。",
        "topics": "economy_macro",
    },
    "crypto": {
        "label": "Crypto",
        "label_zh": "加密",
        "description": "Crypto market headlines anchored on BTC and ETH.",
        "description_zh": "围绕 BTC 和 ETH 的加密市场新闻。",
        "tickers": "CRYPTO:BTC,CRYPTO:ETH",
    },
    "commodities": {
        "label": "Commodities",
        "label_zh": "商品",
        "description": "Energy, transport, and commodity-linked events.",
        "description_zh": "能源、运输与商品链路事件。",
        "topics": "energy_transportation",
    },
}

MACRO_SYMBOLS = {
    "growth": "QQQ",
    "defensive": "XLP",
    "safe_haven": "GLD",
    "dollar": "UUP",
}

MARKET_INTEL_CACHE_PREFIX = "market_intel"


def _cache_key(*parts: object) -> str:
    return ":".join([MARKET_INTEL_CACHE_PREFIX, *[str(part) for part in parts]])

BTC_ETF_SYMBOLS = [
    "IBIT",
    "FBTC",
    "ARKB",
    "BITB",
    "HODL",
    "BRRR",
    "EZBC",
    "BTCW",
]

US_STOCK_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso_z() -> str:
    return _utc_now().isoformat().replace("+00:00", "Z")


def _parse_alpha_timestamp(raw: Optional[str]) -> Optional[str]:
    if not raw or not isinstance(raw, str):
        return None
    value = raw.strip()
    for fmt in ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M"):
        try:
            parsed = datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
            return parsed.isoformat().replace("+00:00", "Z")
        except ValueError:
            continue
    return None


def _alpha_vantage_get(params: dict[str, Any]) -> dict[str, Any]:
    if not ALPHA_VANTAGE_API_KEY or ALPHA_VANTAGE_API_KEY == "demo":
        raise RuntimeError("ALPHA_VANTAGE_API_KEY is not configured")
    response = requests.get(
        ALPHA_VANTAGE_BASE_URL,
        params={**params, "apikey": ALPHA_VANTAGE_API_KEY},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict):
        error_message = payload.get("Error Message") or payload.get("Information") or payload.get("Note")
        if error_message:
            raise RuntimeError(str(error_message))
    return payload


def _extract_openrouter_text(response: Any) -> str:
    choices = getattr(response, "choices", None)
    if choices is None and isinstance(response, dict):
        choices = response.get("choices")
    if not choices:
        return ""

    first_choice = choices[0]
    message = getattr(first_choice, "message", None)
    if message is None and isinstance(first_choice, dict):
        message = first_choice.get("message")
    if message is None:
        return ""

    content = getattr(message, "content", None)
    if content is None and isinstance(message, dict):
        content = message.get("content")

    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
        return "\n".join(part.strip() for part in parts if part and part.strip()).strip()
    return ""


def _normalize_news_item(item: dict[str, Any]) -> Optional[dict[str, Any]]:
    title = (item.get("title") or "").strip()
    if not title:
        return None

    url = (item.get("url") or "").strip()
    source = (item.get("source") or "Unknown").strip()
    time_published = _parse_alpha_timestamp(item.get("time_published"))
    if not time_published:
        return None

    ticker_sentiment = []
    for entry in item.get("ticker_sentiment") or []:
        if not isinstance(entry, dict):
            continue
        ticker = (entry.get("ticker") or "").strip()
        if not ticker:
            continue
        ticker_sentiment.append({
            "ticker": ticker,
            "relevance_score": float(entry.get("relevance_score") or 0),
            "sentiment_score": float(entry.get("ticker_sentiment_score") or 0),
            "sentiment_label": entry.get("ticker_sentiment_label"),
        })

    topics = []
    for entry in item.get("topics") or []:
        if not isinstance(entry, dict):
            continue
        topic = (entry.get("topic") or "").strip()
        if topic:
            topics.append({
                "topic": topic,
                "relevance_score": float(entry.get("relevance_score") or 0),
            })

    return {
        "title": title,
        "url": url,
        "source": source,
        "summary": (item.get("summary") or "").strip(),
        "banner_image": item.get("banner_image"),
        "time_published": time_published,
        "overall_sentiment_score": float(item.get("overall_sentiment_score") or 0),
        "overall_sentiment_label": item.get("overall_sentiment_label"),
        "ticker_sentiment": ticker_sentiment,
        "topics": topics,
    }


def _format_price_levels(levels: list[float]) -> str:
    return ", ".join(f"{level:.2f}" for level in levels[:3]) if levels else "N/A"


def _build_stock_analysis_fallback_summary(analysis: dict[str, Any]) -> str:
    symbol = analysis["symbol"]
    signal = analysis["signal"]
    bullish = analysis.get("bullish_factors") or []
    risks = analysis.get("risk_factors") or []
    lead_bullish = "; ".join(bullish[:2])
    lead_risks = "; ".join(risks[:2])

    if signal == "buy":
        if lead_risks:
            return f"{symbol} keeps a constructive setup with {lead_bullish or 'trend support'}, but {lead_risks.lower()} still needs monitoring."
        return f"{symbol} keeps a constructive setup with {lead_bullish or 'trend support'}."
    if signal == "hold":
        if lead_bullish and lead_risks:
            return f"{symbol} still has support from {lead_bullish.lower()}, while {lead_risks.lower()} is keeping the setup mixed."
        return f"{symbol} remains constructive, but the setup is not fully aligned yet."
    if signal == "sell":
        if lead_risks:
            return f"{symbol} is weakening as {lead_risks.lower()}. A stronger recovery would require reclaiming short- and medium-term trend support."
        return f"{symbol} is weakening across several core trend inputs."
    if lead_bullish and lead_risks:
        return f"{symbol} is mixed: {lead_bullish.lower()}, but {lead_risks.lower()}."
    return f"{symbol} shows mixed signals and should be monitored."


def _generate_stock_analysis_summary(analysis: dict[str, Any]) -> str:
    fallback_summary = _build_stock_analysis_fallback_summary(analysis)
    if not OPENROUTER_API_KEY or not OPENROUTER_MODEL or OpenRouter is None:
        return fallback_summary

    prompt = (
        "Write one concise market snapshot paragraph in English for a trading dashboard.\n"
        "Rules:\n"
        "- Keep it under 60 words.\n"
        "- Be specific and grounded only in the supplied metrics.\n"
        "- Mention the strongest support and strongest risk.\n"
        "- Do not use bullet points.\n"
        "- Do not mention AI, models, or uncertainty disclaimers.\n\n"
        f"Symbol: {analysis['symbol']}\n"
        f"Signal: {analysis['signal']}\n"
        f"Trend status: {analysis['trend_status']}\n"
        f"Signal score: {analysis['signal_score']}\n"
        f"Current price: {analysis['current_price']}\n"
        f"5d return: {analysis['return_5d_pct']}%\n"
        f"20d return: {analysis['return_20d_pct']}%\n"
        f"Moving averages: {json.dumps(analysis.get('moving_averages') or {}, ensure_ascii=True)}\n"
        f"Support levels: {_format_price_levels(analysis.get('support_levels') or [])}\n"
        f"Resistance levels: {_format_price_levels(analysis.get('resistance_levels') or [])}\n"
        f"Bullish factors: {json.dumps(analysis.get('bullish_factors') or [], ensure_ascii=True)}\n"
        f"Risk factors: {json.dumps(analysis.get('risk_factors') or [], ensure_ascii=True)}\n"
    )

    try:
        with OpenRouter(api_key=OPENROUTER_API_KEY) as client:
            response = client.chat.send(
                model=OPENROUTER_MODEL,
                messages=[{"role": "user", "content": prompt}],
            )
        content = _extract_openrouter_text(response)
        return content[:500].strip() if content else fallback_summary
    except Exception:
        return fallback_summary


def _dedupe_news_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in sorted(items, key=lambda row: row["time_published"], reverse=True):
        dedupe_key = item["url"] or f'{item["title"]}::{item["source"]}'
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        deduped.append(item)
    return deduped


def _build_news_summary(category: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    source_counter = Counter(item["source"] for item in items if item.get("source"))
    symbol_counter = Counter()
    sentiment_counter = Counter()

    for item in items:
        sentiment_label = (item.get("overall_sentiment_label") or "neutral").lower()
        sentiment_counter[sentiment_label] += 1
        for entry in item.get("ticker_sentiment") or []:
            ticker = entry.get("ticker")
            if ticker:
                symbol_counter[ticker] += 1

    top_headline = items[0]["title"] if items else None
    latest_item_time = items[0]["time_published"] if items else None

    if len(items) >= 16:
        activity_level = "elevated"
    elif len(items) >= 8:
        activity_level = "active"
    elif len(items) > 0:
        activity_level = "calm"
    else:
        activity_level = "quiet"

    return {
        "category": category,
        "item_count": len(items),
        "activity_level": activity_level,
        "top_headline": top_headline,
        "top_source": source_counter.most_common(1)[0][0] if source_counter else None,
        "highlight_symbols": [ticker for ticker, _ in symbol_counter.most_common(5)],
        "sentiment_breakdown": dict(sentiment_counter),
        "latest_item_time": latest_item_time,
    }


def _fetch_news_feed(category: str, definition: dict[str, str]) -> list[dict[str, Any]]:
    now = _utc_now()
    time_from = (now - timedelta(hours=MARKET_NEWS_LOOKBACK_HOURS)).strftime("%Y%m%dT%H%M")
    params: dict[str, Any] = {
        "function": "NEWS_SENTIMENT",
        "sort": "LATEST",
        "limit": MARKET_NEWS_CATEGORY_LIMIT,
        "time_from": time_from,
    }
    if definition.get("topics"):
        params["topics"] = definition["topics"]
    if definition.get("tickers"):
        params["tickers"] = definition["tickers"]

    payload = _alpha_vantage_get(params)
    feed = payload.get("feed") if isinstance(payload, dict) else None
    if not isinstance(feed, list):
        return []

    normalized_items = []
    for item in feed:
        if not isinstance(item, dict):
            continue
        normalized = _normalize_news_item(item)
        if normalized:
            normalized_items.append(normalized)
    return _dedupe_news_items(normalized_items)


def _fetch_daily_adjusted_series(symbol: str) -> list[dict[str, Any]]:
    payload = _alpha_vantage_get({
        "function": "TIME_SERIES_DAILY_ADJUSTED",
        "symbol": symbol,
        "outputsize": "compact",
    })
    series = payload.get("Time Series (Daily)") if isinstance(payload, dict) else None
    if not isinstance(series, dict):
        raise RuntimeError(f"Missing daily series for {symbol}")

    rows: list[dict[str, Any]] = []
    for date_str, values in series.items():
        if not isinstance(values, dict):
            continue
        try:
            close_value = float(values.get("5. adjusted close") or values.get("4. close"))
        except (TypeError, ValueError):
            continue
        try:
            volume_value = float(values.get("6. volume") or 0)
        except (TypeError, ValueError):
            volume_value = 0.0
        rows.append({
            "date": date_str,
            "close": close_value,
            "volume": volume_value,
        })
    rows.sort(key=lambda row: row["date"], reverse=True)
    return rows


def _fetch_btc_daily_series() -> list[dict[str, Any]]:
    payload = _alpha_vantage_get({
        "function": "DIGITAL_CURRENCY_DAILY",
        "symbol": "BTC",
        "market": "USD",
    })
    series = payload.get("Time Series (Digital Currency Daily)") if isinstance(payload, dict) else None
    if not isinstance(series, dict):
        raise RuntimeError("Missing BTC daily series")

    rows: list[dict[str, Any]] = []
    for date_str, values in series.items():
        if not isinstance(values, dict):
            continue
        close_value = None
        for key in (
            "4b. close (USD)",
            "4a. close (USD)",
            "4. close",
        ):
            try:
                candidate = values.get(key)
                if candidate is None:
                    continue
                close_value = float(candidate)
                break
            except (TypeError, ValueError):
                continue
        if close_value is None:
            continue
        rows.append({
            "date": date_str,
            "close": close_value,
        })
    rows.sort(key=lambda row: row["date"], reverse=True)
    return rows


def _calc_return_pct(series: list[dict[str, Any]], lookback_days: int) -> Optional[float]:
    if len(series) <= lookback_days:
        return None
    latest = float(series[0]["close"])
    previous = float(series[lookback_days]["close"])
    if previous == 0:
        return None
    return ((latest / previous) - 1.0) * 100.0


def _calc_average_volume(series: list[dict[str, Any]], start_index: int, count: int) -> Optional[float]:
    window = [float(row.get("volume") or 0) for row in series[start_index:start_index + count] if float(row.get("volume") or 0) > 0]
    if not window:
        return None
    return sum(window) / len(window)


def _calc_simple_moving_average(series: list[dict[str, Any]], window: int) -> Optional[float]:
    closes = [float(row["close"]) for row in series[:window]]
    if len(closes) < window:
        return None
    return sum(closes) / window


def _normalize_us_stock_symbol(symbol: Optional[str]) -> Optional[str]:
    if not symbol or not isinstance(symbol, str):
        return None
    normalized = symbol.strip().upper()
    if not normalized or not US_STOCK_SYMBOL_RE.match(normalized):
        return None
    return normalized


def _extract_signal_symbols(row: Any) -> list[str]:
    extracted: list[str] = []
    primary = _normalize_us_stock_symbol(row["symbol"] if "symbol" in row.keys() else None)
    if primary:
        extracted.append(primary)

    raw_symbols = row["symbols"] if "symbols" in row.keys() else None
    if raw_symbols:
        try:
            parsed = json.loads(raw_symbols)
            if isinstance(parsed, list):
                for symbol in parsed:
                    normalized = _normalize_us_stock_symbol(str(symbol))
                    if normalized and normalized not in extracted:
                        extracted.append(normalized)
        except Exception:
            pass

    return extracted


def _get_hot_us_stock_symbols(limit: int = 10) -> list[str]:
    scores: Counter[str] = Counter()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT symbol, symbols, message_type
            FROM signals
            WHERE market = 'us-stock'
            """
        )
        signal_rows = cursor.fetchall()
        for row in signal_rows:
            weight = 2
            message_type = row["message_type"]
            if message_type == "discussion":
                weight = 3
            elif message_type == "strategy":
                weight = 4
            elif message_type == "operation":
                weight = 2
            for symbol in _extract_signal_symbols(row):
                scores[symbol] += weight

        cursor.execute(
            """
            SELECT symbol, COUNT(DISTINCT agent_id) AS holder_count
            FROM positions
            WHERE market = 'us-stock'
            GROUP BY symbol
            """
        )
        position_rows = cursor.fetchall()
        for row in position_rows:
            symbol = _normalize_us_stock_symbol(row["symbol"])
            if symbol:
                scores[symbol] += int(row["holder_count"] or 0) * 5
    finally:
        conn.close()

    ranked = [symbol for symbol, _ in scores.most_common(limit)]
    if ranked:
        return ranked[:limit]
    return FALLBACK_STOCK_ANALYSIS_SYMBOLS[:limit]


def _macro_news_tone_signal() -> dict[str, Any]:
    snapshot = _load_latest_news_snapshot("macro")
    if not snapshot:
        return {
            "id": "macro_news_tone",
            "label": "Macro news tone",
            "label_zh": "宏观新闻语气",
            "status": "neutral",
            "value": None,
            "explanation": "Macro news snapshot is not available yet.",
            "explanation_zh": "宏观新闻快照暂未生成。",
            "source": "market_news_snapshots",
        }

    breakdown = (snapshot.get("summary") or {}).get("sentiment_breakdown") or {}
    positive = 0
    negative = 0
    for key, value in breakdown.items():
        normalized = str(key).lower()
        count = int(value or 0)
        if "bearish" in normalized:
            negative += count
        elif "bullish" in normalized:
            positive += count

    tone_score = positive - negative
    if tone_score >= 2:
        status = "bullish"
        explanation = "Macro news flow leans constructive."
        explanation_zh = "宏观新闻整体偏积极。"
    elif tone_score <= -2:
        status = "defensive"
        explanation = "Macro news flow leans defensive."
        explanation_zh = "宏观新闻整体偏防御。"
    else:
        status = "neutral"
        explanation = "Macro news flow is mixed."
        explanation_zh = "宏观新闻整体偏中性。"

    return {
        "id": "macro_news_tone",
        "label": "Macro news tone",
        "label_zh": "宏观新闻语气",
        "status": status,
        "value": tone_score,
        "explanation": explanation,
        "explanation_zh": explanation_zh,
        "source": "market_news_snapshots",
        "as_of": snapshot.get("created_at"),
    }


def _build_etf_flow_snapshot() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    etf_rows: list[dict[str, Any]] = []

    for symbol in BTC_ETF_SYMBOLS:
        series = _fetch_daily_adjusted_series(symbol)
        if len(series) <= ETF_FLOW_BASELINE_VOLUME_DAYS:
            continue

        latest = series[0]
        previous = series[ETF_FLOW_LOOKBACK_DAYS]
        latest_close = float(latest["close"])
        previous_close = float(previous["close"])
        latest_volume = float(latest.get("volume") or 0)
        avg_volume = _calc_average_volume(series, 1, ETF_FLOW_BASELINE_VOLUME_DAYS) or latest_volume or 1.0

        if previous_close == 0:
            continue

        price_change_pct = ((latest_close / previous_close) - 1.0) * 100.0
        volume_ratio = latest_volume / avg_volume if avg_volume else 1.0
        estimated_flow_score = price_change_pct * max(volume_ratio, 0.1)

        if estimated_flow_score >= 2.5:
            direction = "inflow"
        elif estimated_flow_score <= -2.5:
            direction = "outflow"
        else:
            direction = "mixed"

        etf_rows.append({
            "symbol": symbol,
            "price_change_pct": round(price_change_pct, 2),
            "latest_volume": int(latest_volume),
            "avg_volume": int(avg_volume),
            "volume_ratio": round(volume_ratio, 2),
            "estimated_flow_score": round(estimated_flow_score, 2),
            "direction": direction,
            "as_of": latest["date"],
        })

    etf_rows.sort(key=lambda row: abs(float(row["estimated_flow_score"])), reverse=True)

    inflow_count = sum(1 for row in etf_rows if row["direction"] == "inflow")
    outflow_count = sum(1 for row in etf_rows if row["direction"] == "outflow")
    net_score = round(sum(float(row["estimated_flow_score"]) for row in etf_rows), 2)

    if inflow_count >= outflow_count + 2 and net_score > 0:
        direction = "inflow"
        summary_text = "Estimated BTC ETF flow leans positive."
        summary_text_zh = "估算的 BTC ETF 资金方向整体偏流入。"
    elif outflow_count >= inflow_count + 2 and net_score < 0:
        direction = "outflow"
        summary_text = "Estimated BTC ETF flow leans negative."
        summary_text_zh = "估算的 BTC ETF 资金方向整体偏流出。"
    else:
        direction = "mixed"
        summary_text = "Estimated BTC ETF flow is mixed."
        summary_text_zh = "估算的 BTC ETF 资金方向分化。"

    summary = {
        "direction": direction,
        "summary": summary_text,
        "summary_zh": summary_text_zh,
        "inflow_count": inflow_count,
        "outflow_count": outflow_count,
        "tracked_count": len(etf_rows),
        "net_score": net_score,
        "is_estimated": True,
    }

    return etf_rows, summary


def _build_stock_analysis(symbol: str) -> dict[str, Any]:
    series = _fetch_daily_adjusted_series(symbol)
    if len(series) < 20:
        raise RuntimeError(f"Not enough history for {symbol}")

    current_price = float(series[0]["close"])
    ma5 = _calc_simple_moving_average(series, 5)
    ma10 = _calc_simple_moving_average(series, 10)
    ma20 = _calc_simple_moving_average(series, 20)
    ma60 = _calc_simple_moving_average(series, 60)
    return_5d = _calc_return_pct(series, 5) or 0.0
    return_20d = _calc_return_pct(series, 20) or 0.0

    recent_window = [float(row["close"]) for row in series[:20]]
    support = min(recent_window)
    resistance = max(recent_window)

    bullish_factors: list[str] = []
    risk_factors: list[str] = []
    score = 0.0

    if ma20 and current_price > ma20:
        bullish_factors.append("Price is above the 20-day moving average.")
        score += 1.0
    else:
        risk_factors.append("Price is below the 20-day moving average.")
        score -= 1.0

    if ma60 and current_price > ma60:
        bullish_factors.append("Price is above the 60-day moving average.")
        score += 1.0
    elif ma60:
        risk_factors.append("Price is below the 60-day moving average.")
        score -= 1.0

    if return_5d > 2:
        bullish_factors.append("Short-term momentum is positive.")
        score += 1.0
    elif return_5d < -2:
        risk_factors.append("Short-term momentum weakened materially.")
        score -= 1.0

    if return_20d > 5:
        bullish_factors.append("Monthly trend remains constructive.")
        score += 1.0
    elif return_20d < -5:
        risk_factors.append("Monthly trend remains weak.")
        score -= 1.0

    if ma5 and ma10 and ma20 and ma5 > ma10 > ma20:
        bullish_factors.append("Moving averages are stacked in a bullish order.")
        score += 1.0
    elif ma5 and ma10 and ma20 and ma5 < ma10 < ma20:
        risk_factors.append("Moving averages are stacked in a bearish order.")
        score -= 1.0

    distance_to_support = ((current_price / support) - 1.0) * 100 if support else 0.0
    distance_to_resistance = ((resistance / current_price) - 1.0) * 100 if current_price else 0.0
    if distance_to_resistance < 3:
        risk_factors.append("Price is approaching the recent resistance zone.")
        score -= 0.5
    if distance_to_support < 3:
        bullish_factors.append("Price is holding near recent support.")
        score += 0.5

    if score >= 3:
        signal = "buy"
        trend_status = "bullish"
    elif score >= 1:
        signal = "hold"
        trend_status = "constructive"
    elif score <= -3:
        signal = "sell"
        trend_status = "defensive"
    else:
        signal = "watch"
        trend_status = "mixed"

    analysis = {
        "symbol": symbol,
        "market": "us-stock",
        "current_price": round(current_price, 2),
        "return_5d_pct": round(return_5d, 2),
        "return_20d_pct": round(return_20d, 2),
        "moving_averages": {
            "ma5": round(ma5, 2) if ma5 is not None else None,
            "ma10": round(ma10, 2) if ma10 is not None else None,
            "ma20": round(ma20, 2) if ma20 is not None else None,
            "ma60": round(ma60, 2) if ma60 is not None else None,
        },
        "support_levels": [round(support, 2)],
        "resistance_levels": [round(resistance, 2)],
        "distance_to_support_pct": round(distance_to_support, 2),
        "distance_to_resistance_pct": round(distance_to_resistance, 2),
        "signal": signal,
        "signal_score": round(score, 2),
        "trend_status": trend_status,
        "bullish_factors": bullish_factors,
        "risk_factors": risk_factors,
        "as_of": series[0]["date"],
    }
    analysis["summary"] = _generate_stock_analysis_summary(analysis)
    return analysis


def _build_macro_signals() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    qqq_series = _fetch_daily_adjusted_series(MACRO_SYMBOLS["growth"])
    xlp_series = _fetch_daily_adjusted_series(MACRO_SYMBOLS["defensive"])
    gld_series = _fetch_daily_adjusted_series(MACRO_SYMBOLS["safe_haven"])
    uup_series = _fetch_daily_adjusted_series(MACRO_SYMBOLS["dollar"])
    btc_series = _fetch_btc_daily_series()

    qqq_return = _calc_return_pct(qqq_series, MACRO_SIGNAL_LOOKBACK_DAYS)
    xlp_return = _calc_return_pct(xlp_series, MACRO_SIGNAL_LOOKBACK_DAYS)
    gld_return = _calc_return_pct(gld_series, MACRO_SIGNAL_LOOKBACK_DAYS)
    uup_return = _calc_return_pct(uup_series, MACRO_SIGNAL_LOOKBACK_DAYS)
    btc_return = _calc_return_pct(btc_series, BTC_MACRO_LOOKBACK_DAYS)

    signals: list[dict[str, Any]] = []

    if btc_return is not None:
        if btc_return >= 4:
            status = "bullish"
            explanation = "BTC momentum remains positive over the last week."
            explanation_zh = "BTC 最近一周动量偏强。"
        elif btc_return <= -4:
            status = "defensive"
            explanation = "BTC weakened materially over the last week."
            explanation_zh = "BTC 最近一周明显走弱。"
        else:
            status = "neutral"
            explanation = "BTC momentum is mixed."
            explanation_zh = "BTC 动量偏中性。"
        signals.append({
            "id": "btc_trend",
            "label": "BTC trend",
            "label_zh": "BTC 趋势",
            "status": status,
            "value": round(btc_return, 2),
            "unit": "%",
            "lookback_days": BTC_MACRO_LOOKBACK_DAYS,
            "explanation": explanation,
            "explanation_zh": explanation_zh,
            "source": "DIGITAL_CURRENCY_DAILY",
            "as_of": btc_series[0]["date"],
        })

    if qqq_return is not None:
        if qqq_return >= 3:
            status = "bullish"
            explanation = "Growth equities are trending higher."
            explanation_zh = "成长股整体趋势向上。"
        elif qqq_return <= -3:
            status = "defensive"
            explanation = "Growth equities are losing momentum."
            explanation_zh = "成长股动量明显转弱。"
        else:
            status = "neutral"
            explanation = "Growth equity momentum is mixed."
            explanation_zh = "成长股动量偏中性。"
        signals.append({
            "id": "qqq_trend",
            "label": "QQQ trend",
            "label_zh": "QQQ 趋势",
            "status": status,
            "value": round(qqq_return, 2),
            "unit": "%",
            "lookback_days": MACRO_SIGNAL_LOOKBACK_DAYS,
            "explanation": explanation,
            "explanation_zh": explanation_zh,
            "source": "TIME_SERIES_DAILY_ADJUSTED",
            "as_of": qqq_series[0]["date"],
        })

    if qqq_return is not None and xlp_return is not None:
        spread = qqq_return - xlp_return
        if spread >= 2:
            status = "bullish"
            explanation = "Growth is outperforming defensive staples."
            explanation_zh = "成长板块显著跑赢防御消费。"
        elif spread <= -2:
            status = "defensive"
            explanation = "Defensive staples are outperforming growth."
            explanation_zh = "防御消费跑赢成长板块。"
        else:
            status = "neutral"
            explanation = "Growth and defensive sectors are balanced."
            explanation_zh = "成长与防御板块相对均衡。"
        signals.append({
            "id": "qqq_vs_xlp",
            "label": "QQQ vs XLP",
            "label_zh": "QQQ 相对 XLP",
            "status": status,
            "value": round(spread, 2),
            "unit": "spread_pct",
            "lookback_days": MACRO_SIGNAL_LOOKBACK_DAYS,
            "explanation": explanation,
            "explanation_zh": explanation_zh,
            "source": "TIME_SERIES_DAILY_ADJUSTED",
            "as_of": qqq_series[0]["date"],
        })

    if gld_return is not None and uup_return is not None:
        safe_haven_strength = max(gld_return, uup_return)
        if safe_haven_strength >= 3:
            status = "defensive"
            explanation = "Safe-haven assets are bid."
            explanation_zh = "避险资产出现明显走强。"
        elif safe_haven_strength <= 0:
            status = "bullish"
            explanation = "Safe-haven demand is subdued."
            explanation_zh = "避险需求偏弱。"
        else:
            status = "neutral"
            explanation = "Safe-haven demand is present but not dominant."
            explanation_zh = "避险需求存在，但并不极端。"
        signals.append({
            "id": "safe_haven_pressure",
            "label": "Safe-haven pressure",
            "label_zh": "避险压力",
            "status": status,
            "value": round(safe_haven_strength, 2),
            "unit": "%",
            "lookback_days": MACRO_SIGNAL_LOOKBACK_DAYS,
            "explanation": explanation,
            "explanation_zh": explanation_zh,
            "source": "TIME_SERIES_DAILY_ADJUSTED",
            "as_of": gld_series[0]["date"],
        })

    signals.append(_macro_news_tone_signal())

    bullish_count = sum(1 for signal in signals if signal.get("status") == "bullish")
    defensive_count = sum(1 for signal in signals if signal.get("status") == "defensive")
    total_count = len(signals)

    if bullish_count >= defensive_count + 2:
        verdict = "bullish"
        summary = "Risk appetite is leading across the current macro snapshot."
        summary_zh = "当前宏观快照整体偏向风险偏好。"
    elif defensive_count >= bullish_count + 2:
        verdict = "defensive"
        summary = "Defensive pressure dominates the current macro snapshot."
        summary_zh = "当前宏观快照整体偏向防御。"
    else:
        verdict = "neutral"
        summary = "Macro signals are mixed and do not show a clear regime."
        summary_zh = "当前宏观信号分化，尚未形成明确主导方向。"

    meta = {
        "summary": summary,
        "summary_zh": summary_zh,
        "defensive_count": defensive_count,
        "latest_prices": {
            "BTC": btc_series[0]["close"] if btc_series else None,
            "QQQ": qqq_series[0]["close"] if qqq_series else None,
            "XLP": xlp_series[0]["close"] if xlp_series else None,
            "GLD": gld_series[0]["close"] if gld_series else None,
            "UUP": uup_series[0]["close"] if uup_series else None,
        },
    }

    source = {
        "alpha_vantage_functions": [
            "TIME_SERIES_DAILY_ADJUSTED",
            "DIGITAL_CURRENCY_DAILY",
        ],
        "news_dependency": "market_news_snapshots.macro",
    }

    return signals, {
        "verdict": verdict,
        "bullish_count": bullish_count,
        "total_count": total_count,
        "meta": meta,
        "source": source,
    }


def _prune_market_news_history(cursor) -> None:
    for category in NEWS_CATEGORY_DEFINITIONS:
        cursor.execute(
            """
            DELETE FROM market_news_snapshots
            WHERE category = ?
              AND id NOT IN (
                SELECT id
                FROM market_news_snapshots
                WHERE category = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
              )
            """,
            (category, category, MARKET_NEWS_HISTORY_PER_CATEGORY),
        )


def refresh_market_news_snapshots() -> dict[str, Any]:
    """
    Fetch and persist the latest market-news snapshots.
    Returns a small status payload for logging.
    """
    inserted = 0
    errors: dict[str, str] = {}
    created_at = _utc_now_iso_z()
    rows_to_insert: list[tuple[str, str, str, str, str]] = []

    for category, definition in NEWS_CATEGORY_DEFINITIONS.items():
        try:
            items = _fetch_news_feed(category, definition)
            summary = _build_news_summary(category, items)
            snapshot_key = f"{category}:{created_at}"
            rows_to_insert.append((
                category,
                snapshot_key,
                json.dumps(items, ensure_ascii=True),
                json.dumps(summary, ensure_ascii=True),
                created_at,
            ))
            inserted += 1
        except Exception as exc:
            errors[category] = str(exc)

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if rows_to_insert:
            cursor.executemany(
                """
                INSERT INTO market_news_snapshots (category, snapshot_key, items_json, summary_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                rows_to_insert,
            )
        _prune_market_news_history(cursor)
        conn.commit()
    finally:
        conn.close()

    delete_pattern(_cache_key("news", "*"))
    delete_pattern(_cache_key("overview"))

    return {
        "inserted_categories": inserted,
        "errors": errors,
        "created_at": created_at,
    }


def _load_latest_news_snapshot(category: str) -> Optional[dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT category, items_json, summary_json, created_at
            FROM market_news_snapshots
            WHERE category = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (category,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "category": row["category"],
            "items": json.loads(row["items_json"] or "[]"),
            "summary": json.loads(row["summary_json"] or "{}"),
            "created_at": row["created_at"],
        }
    finally:
        conn.close()


def _prune_macro_signal_history(cursor) -> None:
    cursor.execute(
        """
        DELETE FROM macro_signal_snapshots
        WHERE id NOT IN (
            SELECT id
            FROM macro_signal_snapshots
            ORDER BY created_at DESC, id DESC
            LIMIT ?
        )
        """,
        (MACRO_SIGNAL_HISTORY_LIMIT,),
    )


def _prune_etf_flow_history(cursor) -> None:
    cursor.execute(
        """
        DELETE FROM etf_flow_snapshots
        WHERE id NOT IN (
            SELECT id
            FROM etf_flow_snapshots
            ORDER BY created_at DESC, id DESC
            LIMIT ?
        )
        """,
        (ETF_FLOW_HISTORY_LIMIT,),
    )


def _prune_stock_analysis_history(cursor) -> None:
    cursor.execute("SELECT DISTINCT symbol FROM stock_analysis_snapshots")
    symbols = [row["symbol"] for row in cursor.fetchall() if row["symbol"]]
    for symbol in symbols:
        cursor.execute(
            """
            DELETE FROM stock_analysis_snapshots
            WHERE symbol = ?
              AND id NOT IN (
                SELECT id
                FROM stock_analysis_snapshots
                WHERE symbol = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
              )
            """,
            (symbol, symbol, STOCK_ANALYSIS_HISTORY_LIMIT),
        )


def refresh_macro_signal_snapshot() -> dict[str, Any]:
    signals, snapshot = _build_macro_signals()
    created_at = _utc_now_iso_z()
    snapshot_key = f'macro:{created_at}'

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO macro_signal_snapshots (
                snapshot_key, verdict, bullish_count, total_count,
                signals_json, meta_json, source_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_key,
                snapshot["verdict"],
                snapshot["bullish_count"],
                snapshot["total_count"],
                json.dumps(signals, ensure_ascii=True),
                json.dumps(snapshot["meta"], ensure_ascii=True),
                json.dumps(snapshot["source"], ensure_ascii=True),
                created_at,
            ),
        )
        _prune_macro_signal_history(cursor)
        conn.commit()
    finally:
        conn.close()

    delete_pattern(_cache_key("macro_signals"))
    delete_pattern(_cache_key("overview"))

    return {
        "verdict": snapshot["verdict"],
        "bullish_count": snapshot["bullish_count"],
        "total_count": snapshot["total_count"],
        "created_at": created_at,
    }


def get_macro_signals_payload() -> dict[str, Any]:
    cache_key = _cache_key("macro_signals")
    cached = get_json(cache_key)
    if isinstance(cached, dict):
        return cached

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT verdict, bullish_count, total_count, signals_json, meta_json, source_json, created_at
            FROM macro_signal_snapshots
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone()
        if not row:
            payload = {
                "available": False,
                "verdict": "unavailable",
                "bullish_count": 0,
                "total_count": 0,
                "signals": [],
                "meta": {},
                "source": {},
                "created_at": None,
            }
            set_json(cache_key, payload, ttl_seconds=MACRO_SIGNAL_CACHE_TTL_SECONDS)
            return payload
        payload = {
            "available": True,
            "verdict": row["verdict"],
            "bullish_count": row["bullish_count"],
            "total_count": row["total_count"],
            "signals": json.loads(row["signals_json"] or "[]"),
            "meta": json.loads(row["meta_json"] or "{}"),
            "source": json.loads(row["source_json"] or "{}"),
            "created_at": row["created_at"],
        }
        set_json(cache_key, payload, ttl_seconds=MACRO_SIGNAL_CACHE_TTL_SECONDS)
        return payload
    finally:
        conn.close()


def refresh_etf_flow_snapshot() -> dict[str, Any]:
    etfs, summary = _build_etf_flow_snapshot()
    created_at = _utc_now_iso_z()
    snapshot_key = f'etf:{created_at}'

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO etf_flow_snapshots (snapshot_key, summary_json, etfs_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                snapshot_key,
                json.dumps(summary, ensure_ascii=True),
                json.dumps(etfs, ensure_ascii=True),
                created_at,
            ),
        )
        _prune_etf_flow_history(cursor)
        conn.commit()
    finally:
        conn.close()

    delete_pattern(_cache_key("etf_flows"))
    delete_pattern(_cache_key("overview"))

    return {
        "direction": summary["direction"],
        "tracked_count": summary["tracked_count"],
        "created_at": created_at,
    }


def get_etf_flows_payload() -> dict[str, Any]:
    cache_key = _cache_key("etf_flows")
    cached = get_json(cache_key)
    if isinstance(cached, dict):
        return cached

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT summary_json, etfs_json, created_at
            FROM etf_flow_snapshots
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone()
        if not row:
            payload = {
                "available": False,
                "summary": {},
                "etfs": [],
                "created_at": None,
                "is_estimated": True,
            }
            set_json(cache_key, payload, ttl_seconds=ETF_FLOW_CACHE_TTL_SECONDS)
            return payload
        summary = json.loads(row["summary_json"] or "{}")
        payload = {
            "available": True,
            "summary": summary,
            "etfs": json.loads(row["etfs_json"] or "[]"),
            "created_at": row["created_at"],
            "is_estimated": bool(summary.get("is_estimated", True)),
        }
        set_json(cache_key, payload, ttl_seconds=ETF_FLOW_CACHE_TTL_SECONDS)
        return payload
    finally:
        conn.close()


def refresh_stock_analysis_snapshots() -> dict[str, Any]:
    created_at = _utc_now_iso_z()
    inserted = 0
    errors: dict[str, str] = {}
    symbols = _get_hot_us_stock_symbols(limit=10)
    rows_to_insert: list[tuple[Any, ...]] = []

    for symbol in symbols:
        try:
            analysis = _build_stock_analysis(symbol)
            analysis_id = f"{symbol}:{created_at}"
            rows_to_insert.append((
                symbol,
                "us-stock",
                analysis_id,
                analysis["current_price"],
                "USD",
                analysis["signal"],
                analysis["signal_score"],
                analysis["trend_status"],
                json.dumps(analysis["support_levels"], ensure_ascii=True),
                json.dumps(analysis["resistance_levels"], ensure_ascii=True),
                json.dumps(analysis["bullish_factors"], ensure_ascii=True),
                json.dumps(analysis["risk_factors"], ensure_ascii=True),
                analysis["summary"],
                json.dumps(analysis, ensure_ascii=True),
                json.dumps([], ensure_ascii=True),
                created_at,
            ))
            inserted += 1
        except Exception as exc:
            errors[symbol] = str(exc)

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if rows_to_insert:
            cursor.executemany(
                """
                INSERT INTO stock_analysis_snapshots (
                    symbol, market, analysis_id, current_price, currency, signal,
                    signal_score, trend_status, support_levels_json, resistance_levels_json,
                    bullish_factors_json, risk_factors_json, summary_text, analysis_json, news_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows_to_insert,
            )
        _prune_stock_analysis_history(cursor)
        conn.commit()
    finally:
        conn.close()

    delete_pattern(_cache_key("stocks", "*"))
    delete_pattern(_cache_key("overview"))

    return {
        "inserted_symbols": inserted,
        "errors": errors,
        "created_at": created_at,
    }


def get_stock_analysis_latest_payload(symbol: str) -> dict[str, Any]:
    symbol = symbol.strip().upper()
    cache_key = _cache_key("stocks", "latest", symbol)
    cached = get_json(cache_key)
    if isinstance(cached, dict):
        return cached

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT symbol, market, analysis_id, current_price, currency, signal, signal_score,
                   trend_status, support_levels_json, resistance_levels_json, bullish_factors_json,
                   risk_factors_json, summary_text, analysis_json, created_at
            FROM stock_analysis_snapshots
            WHERE symbol = ? AND market = 'us-stock'
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (symbol,),
        )
        row = cursor.fetchone()
        if not row:
            payload = {"available": False, "symbol": symbol}
            set_json(cache_key, payload, ttl_seconds=STOCK_ANALYSIS_CACHE_TTL_SECONDS)
            return payload
        payload = {
            "available": True,
            "symbol": row["symbol"],
            "market": row["market"],
            "analysis_id": row["analysis_id"],
            "current_price": row["current_price"],
            "currency": row["currency"],
            "signal": row["signal"],
            "signal_score": row["signal_score"],
            "trend_status": row["trend_status"],
            "support_levels": json.loads(row["support_levels_json"] or "[]"),
            "resistance_levels": json.loads(row["resistance_levels_json"] or "[]"),
            "bullish_factors": json.loads(row["bullish_factors_json"] or "[]"),
            "risk_factors": json.loads(row["risk_factors_json"] or "[]"),
            "summary": row["summary_text"],
            "analysis": json.loads(row["analysis_json"] or "{}"),
            "created_at": row["created_at"],
        }
        set_json(cache_key, payload, ttl_seconds=STOCK_ANALYSIS_CACHE_TTL_SECONDS)
        return payload
    finally:
        conn.close()


def get_stock_analysis_history_payload(symbol: str, limit: int = 10) -> dict[str, Any]:
    symbol = symbol.strip().upper()
    normalized_limit = max(1, min(limit, 30))
    cache_key = _cache_key("stocks", "history", symbol, normalized_limit)
    cached = get_json(cache_key)
    if isinstance(cached, dict):
        return cached

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT analysis_id, signal, signal_score, trend_status, summary_text, analysis_json, created_at
            FROM stock_analysis_snapshots
            WHERE symbol = ? AND market = 'us-stock'
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (symbol, normalized_limit),
        )
        rows = cursor.fetchall()
        payload = {
            "available": bool(rows),
            "symbol": symbol,
            "history": [
                {
                    "analysis_id": row["analysis_id"],
                    "signal": row["signal"],
                    "signal_score": row["signal_score"],
                    "trend_status": row["trend_status"],
                    "summary": row["summary_text"],
                    "analysis": json.loads(row["analysis_json"] or "{}"),
                    "created_at": row["created_at"],
                }
                for row in rows
            ],
        }
        set_json(cache_key, payload, ttl_seconds=STOCK_ANALYSIS_CACHE_TTL_SECONDS)
        return payload
    finally:
        conn.close()


def get_featured_stock_analysis_payload(limit: int = 6) -> dict[str, Any]:
    normalized_limit = max(1, min(limit, 10))
    cache_key = _cache_key("stocks", "featured", normalized_limit)
    cached = get_json(cache_key)
    if isinstance(cached, dict):
        return cached

    symbols = _get_hot_us_stock_symbols(limit=normalized_limit)
    payload = {
        "available": True,
        "items": [get_stock_analysis_latest_payload(symbol) for symbol in symbols],
    }
    set_json(cache_key, payload, ttl_seconds=STOCK_ANALYSIS_CACHE_TTL_SECONDS)
    return payload


def get_market_news_payload(category: Optional[str] = None, limit: int = 5) -> dict[str, Any]:
    normalized_category = (category or "").strip().lower() or "all"
    normalized_limit = max(limit, 1)
    cache_key = _cache_key("news", normalized_category, normalized_limit)
    cached = get_json(cache_key)
    if isinstance(cached, dict):
        return cached

    requested_categories = [category] if category else list(NEWS_CATEGORY_DEFINITIONS.keys())
    sections = []

    for category_key in requested_categories:
        definition = NEWS_CATEGORY_DEFINITIONS.get(category_key)
        if not definition:
            continue
        snapshot = _load_latest_news_snapshot(category_key)
        if not snapshot:
            sections.append({
                "category": category_key,
                "label": definition["label"],
                "label_zh": definition["label_zh"],
                "description": definition["description"],
                "description_zh": definition["description_zh"],
                "items": [],
                "summary": {
                    "category": category_key,
                    "item_count": 0,
                    "activity_level": "unavailable",
                },
                "created_at": None,
                "available": False,
            })
            continue

        sections.append({
            "category": category_key,
            "label": definition["label"],
            "label_zh": definition["label_zh"],
            "description": definition["description"],
            "description_zh": definition["description_zh"],
            "items": (snapshot["items"] or [])[: normalized_limit],
            "summary": snapshot["summary"],
            "created_at": snapshot["created_at"],
            "available": True,
        })

    last_updated_at = max((section["created_at"] for section in sections if section.get("created_at")), default=None)
    total_items = sum(int((section.get("summary") or {}).get("item_count") or 0) for section in sections)

    payload = {
        "categories": sections,
        "last_updated_at": last_updated_at,
        "total_items": total_items,
        "available": any(section.get("available") for section in sections),
    }
    set_json(cache_key, payload, ttl_seconds=MARKET_NEWS_CACHE_TTL_SECONDS)
    return payload


def get_market_intel_overview() -> dict[str, Any]:
    cache_key = _cache_key("overview")
    cached = get_json(cache_key)
    if isinstance(cached, dict):
        return cached

    macro_payload = get_macro_signals_payload()
    etf_payload = get_etf_flows_payload()
    stock_payload = get_featured_stock_analysis_payload(limit=4)
    news_payload = get_market_news_payload(limit=3)
    categories = news_payload["categories"]
    total_items = news_payload["total_items"]
    available_categories = [section for section in categories if section.get("available")]

    if total_items >= 20:
        news_status = "elevated"
    elif total_items >= 8:
        news_status = "active"
    elif total_items > 0:
        news_status = "calm"
    else:
        news_status = "quiet"

    top_sources = Counter()
    latest_headline = None
    latest_item_time = None

    for section in categories:
        summary = section.get("summary") or {}
        source = summary.get("top_source")
        if source:
            top_sources[source] += 1

        for item in section.get("items") or []:
            item_time = item.get("time_published")
            if not item_time:
                continue
            if latest_item_time is None or item_time > latest_item_time:
                latest_item_time = item_time
                latest_headline = item.get("title")

    payload = {
        "available": bool(available_categories) or bool(macro_payload.get("available")),
        "last_updated_at": max(
            [timestamp for timestamp in (news_payload["last_updated_at"], macro_payload.get("created_at")) if timestamp],
            default=None,
        ),
        "macro_verdict": macro_payload.get("verdict"),
        "macro_bullish_count": macro_payload.get("bullish_count", 0),
        "macro_total_count": macro_payload.get("total_count", 0),
        "macro_summary": (macro_payload.get("meta") or {}).get("summary"),
        "macro_summary_zh": (macro_payload.get("meta") or {}).get("summary_zh"),
        "etf_direction": (etf_payload.get("summary") or {}).get("direction"),
        "etf_summary": (etf_payload.get("summary") or {}).get("summary"),
        "etf_summary_zh": (etf_payload.get("summary") or {}).get("summary_zh"),
        "etf_tracked_count": (etf_payload.get("summary") or {}).get("tracked_count", 0),
        "featured_stock_count": len([item for item in stock_payload.get("items", []) if item.get("available")]),
        "news_status": news_status,
        "headline_count": total_items,
        "active_categories": len(available_categories),
        "top_source": top_sources.most_common(1)[0][0] if top_sources else None,
        "latest_headline": latest_headline,
        "latest_item_time": latest_item_time,
        "categories": [
            {
                "category": section["category"],
                "label": section["label"],
                "label_zh": section["label_zh"],
                "activity_level": (section.get("summary") or {}).get("activity_level", "quiet"),
                "item_count": (section.get("summary") or {}).get("item_count", 0),
                "top_headline": (section.get("summary") or {}).get("top_headline"),
                "top_source": (section.get("summary") or {}).get("top_source"),
                "created_at": section.get("created_at"),
            }
                for section in categories
        ],
    }
    set_json(cache_key, payload, ttl_seconds=MARKET_INTEL_OVERVIEW_CACHE_TTL_SECONDS)
    return payload
