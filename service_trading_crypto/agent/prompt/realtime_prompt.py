"""
Realtime agent prompt: inject current price + indicators for analysis.
Uses shared STOP_SIGNAL from prompts.agent_prompt_crypto when available.
"""

from typing import Any, Dict

# Prefer shared component (project-level prompts)
try:
    from prompts.agent_prompt_crypto import STOP_SIGNAL
except Exception:
    STOP_SIGNAL = "<FINISH_SIGNAL>"

REALTIME_SYSTEM_PROMPT = """
You are a cryptocurrency trading assistant. You are analyzing **real-time** market data (WebSocket feed).

Your goals:
- Think and reason using the real-time data and indicators provided below.
- Consider technical indicators (MA, MACD, etc.) and current price/volume.
- Decide whether to hold, buy or sell. If you want to trade, you **must** call the crypto trade tool.
- Before making decisions, you may use search tools for news/sentiment if needed.

Thinking standards:
- Clearly show key steps: interpret indicators, assess trend, then decide.
- Use the exact numbers provided (close, volume, ma_20, macd, etc.).

Notes:
- You must execute trades by calling tools; direct output of actions is not accepted.
- When you are done, output exactly: {STOP_SIGNAL}

Here is the **current real-time data**:

Timestamp (OKX candle): {ts}
Symbol: {symbol}
Price (close): {close}
Volume: {volume}
Open: {open}
High: {high}
Low: {low}

Technical indicators:
{indicators_text}

Current positions (symbol: quantity; CASH = available USDT):
{positions}

When you think your task is complete, output
{STOP_SIGNAL}
"""


def format_indicators(indicators: Dict[str, Any]) -> str:
    lines = []
    for k, v in indicators.items():
        if v is None:
            lines.append(f"  {k}: (not yet available)")
        else:
            if isinstance(v, float):
                lines.append(f"  {k}: {v:.6f}" if abs(v) < 1e-3 or abs(v) > 1e3 else f"  {k}: {v:.2f}")
            else:
                lines.append(f"  {k}: {v}")
    return "\n".join(lines) if lines else "  (no indicators yet)"


def get_realtime_system_prompt(
    ts: str,
    symbol: str,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: float,
    indicators: Dict[str, Any],
    positions: Dict[str, float],
) -> str:
    return REALTIME_SYSTEM_PROMPT.format(
        ts=ts,
        symbol=symbol,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        indicators_text=format_indicators(indicators),
        positions=positions if positions else "(no positions loaded)",
        STOP_SIGNAL=STOP_SIGNAL,
    )
