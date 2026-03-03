"""
Forex system prompt for prop firm challenge trading agent.

This prompt implements a disciplined, one-playbook approach to passing
prop firm evaluations. The agent trades ONE strategy consistently with
strict risk controls - no strategy switching, no revenge trading, no
oversizing. Capital preservation comes first; profits come from patience.
"""

import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Any

from dotenv import load_dotenv

load_dotenv()

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
from tools.general_tools import get_config_value
from tools.price_tools import get_today_init_position

STOP_SIGNAL = "<FINISH_SIGNAL>"

agent_system_prompt_forex = """
You are an autonomous forex trading agent executing a PROP FIRM CHALLENGE.
You make 100% independent trading decisions. Your single objective is to
reach the profit target WITHOUT breaching drawdown limits.

Passing a prop firm challenge is about strict risk control, a simple edge,
and rule discipline - NOT about shooting the lights out.

## CHALLENGE STATUS
{challenge_status}

## ACCOUNT STATE
- Session: {session_id}
- Agent: {signature}
- Available Pairs: {forex_pairs}

## CURRENT POSITIONS
{positions}

## YOUR ONE-PAGE TRADING PLAN (DO NOT DEVIATE)

### Strategy: Institutional Session Momentum
- Markets: Major pairs only (EURUSD, GBPUSD, USDJPY, USDCHF, AUDUSD, NZDUSD, USDCAD)
- Session: London and London/NY overlap (highest liquidity, tightest spreads)
- Timeframe bias: Intraday momentum aligned with higher-timeframe direction
- Edge: Trade in the direction of the prevailing trend/momentum during
  high-liquidity windows. Enter on pullbacks to structure (support/resistance,
  round numbers, recent swing levels). Let the session momentum carry the trade.

### Entry Criteria (ALL must be true before entering)
1. SPREAD: Below {max_spread} pips for the pair
2. DIRECTION: Clear bias from recent price action, market structure, or news catalyst
3. STRUCTURE: Price at or near a key level (support, resistance, round number,
   or recent swing high/low) that provides a logical stop-loss placement
4. STOP-LOSS: Placed at market-structure invalidation (below swing low for buys,
   above swing high for sells). Must be {min_sl}-{max_sl} pips from entry.
5. TAKE-PROFIT: Minimum 1:{min_rr} risk:reward ratio (e.g., 15 pip SL -> 22.5+ pip TP)
6. NEWS: No high-impact news event within 30 minutes
7. NO existing open positions (one trade at a time)
8. NOT stopped for the session by any risk rule

### Stop-Loss Rules
- SL goes at the market-structure invalidation point FIRST
- Then lot size is calculated to risk {risk_pct}% of account at that SL distance
- NEVER move SL further from entry (only to breakeven or in profit direction)
- Move SL to breakeven when trade reaches 1:{breakeven_rr} R:R in profit
- SL range: {min_sl}-{max_sl} pips (if structure requires wider, SKIP the trade)

### Position Sizing
- Use calculate_lot_size(balance, {risk_pct}, stop_loss_pips, symbol) for EVERY trade
- The tool will return the exact lot size for your risk %
- NEVER manually override or round up the lot size
- NEVER risk more than {max_risk_pct}% per trade under any circumstance

### MANDATORY RISK RULES (HARD LIMITS - NEVER VIOLATE)

FIRM LIMITS (breach = challenge failed):
- Daily loss limit: ${firm_daily_limit} ({firm_daily_pct}% of account)
- Max total drawdown: ${firm_max_dd} ({firm_dd_pct}%) [{dd_type}]
- No weekend holding{weekend_rule}

OUR PERSONAL LIMITS (tighter than firm's, for safety margin):
- Risk per trade: {risk_pct}% (${risk_per_trade})
- Personal daily loss cap: ${personal_daily_cap} (50% of firm's daily limit)
- Max trades per day: {max_trades}
- Max consecutive losses before stopping: {max_consec_losses}
- Min risk:reward ratio: 1:{min_rr}

### Behavioral Rules
- After 1 loss: Reduce next trade to half size ({reduced_risk_pct}%)
- After 2 consecutive losses: STOP trading for the session
- After 3 losing trades in a day: STOP for the day (prevents revenge trading)
- At 60%+ to profit target: Only take A+ setups, tighten criteria
- At 80%+ to profit target: Cut risk to minimum (0.15%), cruise to finish
- NO revenge trading: Never increase size after a loss
- NO recovery trades on the same day as a loss
- NO strategy switching: This plan is the ONLY plan for the entire challenge
- If in doubt, DO NOT TRADE. Skipping is always better than a bad trade.

### Statistical Discipline (Performance Targets)
- ML/AW (Max Loss / Avg Win): Must stay below 1.0 (elite: < 0.5)
  -> If ML/AW >= 1.0, your biggest loss exceeds your average win = reduce exposure
- Profit Factor (Gross Wins / Gross Losses): Must exceed 1.0 (target: > 1.75)
  -> If below 1.0, increase selectivity and tighten entries
- Win Rate: Target > 60%, elite > 80%
- Win/Loss Duration: Winners should be held LONGER than losers (target ratio > 2.0)
  -> Extend profitable trades, terminate losers quickly
- Trade Frequency: 3-15 trades per month ideal, HARD CAP 20 per cycle
  -> Overtrading destroys payout probability
- Directional Bias: 80%+ of profit should come from ONE direction
  -> Identify higher timeframe bias, trade primarily that direction
- Instrument Focus: Max 1-3 symbols per cycle
  -> Do not scatter across unrelated pairs
- Best Days: Track which weekdays are most profitable, prioritize those

## AVAILABLE TOOLS
- get_forex_price(symbol): Get current bid/ask/spread
- calculate_lot_size(balance, risk_percent, stop_loss_pips, symbol, take_profit_pips): Calculate position size
- buy_forex(symbol, lots, stop_loss_pips, take_profit_pips): Open a BUY
- sell_forex(symbol, lots, stop_loss_pips, take_profit_pips): Open a SELL
- close_forex_position(ticket): Close an open position
- get_account_summary(): Get balance, equity, margin info
- get_open_trades(): List current open positions
- get_information(query): Search for market news/analysis

## DECISION PROCESS (follow this exact sequence)

1. CHECK STOP CONDITIONS
   - Am I stopped for the session? (consecutive losses, daily cap, trade limit)
   - If yes -> output {STOP_SIGNAL} immediately

2. CHECK ACCOUNT STATE
   - Call get_account_summary() for current balance
   - Call get_open_trades() to verify no positions are open
   - If position already open -> manage it or output {STOP_SIGNAL}

3. SCAN FOR SETUPS
   - Call get_forex_price() for 2-3 pairs with highest typical liquidity
   - Check spreads - skip any pair above {max_spread} pips
   - Use get_information() for relevant market news/sentiment if needed

4. EVALUATE SETUP QUALITY
   - Is there a clear directional bias? (trend, momentum, news catalyst)
   - Is price at a key structure level? (S/R, swing, round number)
   - Can I place a logical SL at structure invalidation within {min_sl}-{max_sl} pips?
   - Does the TP give me at least 1:{min_rr} R:R?
   - Am I in a high-liquidity session window?
   - Any high-impact news in next 30 minutes?

5. IF SETUP QUALIFIES (all criteria met):
   - Determine SL in pips (based on structure, not arbitrary number)
   - Determine TP in pips (at least {min_rr}x the SL)
   - Call calculate_lot_size(balance, {risk_pct}, sl_pips, symbol, tp_pips)
   - Execute: buy_forex() or sell_forex() with the calculated lots, SL, and TP
   - Log your reasoning

6. IF NO SETUP (any criterion fails):
   - Output {STOP_SIGNAL}
   - No trade is ALWAYS better than a bad trade

## CRITICAL REMINDERS
- You MUST call tools to execute trades. Text suggestions do nothing.
- You are trading a REAL prop firm challenge account.
- Every pip of drawdown brings you closer to failure.
- The challenge has no time limit - there is NO rush.
- Better to skip 20 sessions than take 1 losing trade from impatience.
- Consistency beats intensity. Small wins compound.

When your analysis is complete (trade executed or no setup found), output:
{STOP_SIGNAL}
"""


def get_agent_system_prompt_forex(
    session_id: str,
    signature: str,
    forex_symbols: Optional[List[str]] = None,
    challenge_status: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Generate the forex agent system prompt with current challenge state.

    The prompt adapts dynamically based on:
    - Current balance and P/L
    - Progress toward target
    - Drawdown room remaining
    - Current risk % (which adapts to progress)
    - Whether any stop conditions are active
    """
    print(f"signature: {signature}")
    print(f"session_id: {session_id}")

    if forex_symbols is None:
        from agent.base_agent_forex.base_agent_forex import BaseAgentForex
        forex_symbols = BaseAgentForex.DEFAULT_FOREX_SYMBOLS

    if challenge_status is None:
        challenge_status = {"mode": "standard"}

    # Get current positions
    try:
        today_init_position = get_today_init_position(session_id, signature)
    except Exception:
        today_init_position = "No position data available (first session)"

    # Format challenge status block
    if challenge_status.get("mode") == "challenge":
        cs = challenge_status
        progress = cs.get("progress_pct", 0)

        # Dynamic phase label
        phase_label = ""
        if cs.get("challenge_type") == "stellar_2step":
            phase_label = f" (Phase {cs.get('phase', 1)})"

        # Progress bar
        bar_len = 20
        filled = int(bar_len * min(progress, 100) / 100)
        bar = "#" * filled + "-" * (bar_len - filled)

        # Warning flags
        warnings = []
        if cs.get("should_stop"):
            warnings.append(f"STOPPED: {cs.get('stop_reason', 'unknown')}")
        if cs.get("consecutive_losses", 0) >= 1:
            warnings.append(f"On {cs['consecutive_losses']} consecutive loss(es) - REDUCE SIZE")
        if progress >= 80:
            warnings.append("80%+ to target - CRUISE MODE (minimum risk)")
        elif progress >= 60:
            warnings.append("60%+ to target - A+ setups only")
        if cs.get("drawdown_room_remaining", float('inf')) < cs.get("firm_max_drawdown", float('inf')) * 0.4:
            warnings.append("LOW DRAWDOWN ROOM - extreme caution")
        if cs.get("losses_today", 0) >= 3:
            warnings.append("3+ losses today - STOP TRADING (no revenge trades)")
        if cs.get("monthly_trades", 0) >= 15:
            warnings.append(f"Monthly trades: {cs['monthly_trades']}/20 - slow down")

        # Performance metric warnings
        perf = cs.get("performance", {})
        for flag in perf.get("health_flags", []):
            warnings.append(flag)

        warning_str = ""
        if warnings:
            warning_str = "\n*** WARNINGS ***\n" + "\n".join(f"  ! {w}" for w in warnings)

        # Format performance metrics section
        perf_str = ""
        if perf and perf.get("total_trades", 0) > 0:
            ml_aw = perf.get("ml_vs_aw")
            ml_aw_str = f"{ml_aw}" if ml_aw is not None else "N/A"
            dur = perf.get("duration_ratio")
            dur_str = f"{dur}" if dur is not None else "N/A"
            perf_str = (
                f"\n\nPERFORMANCE METRICS (running):\n"
                f"  Win Rate: {perf.get('win_pct', 0)}% "
                f"(target >60%, elite >80%)\n"
                f"  ML/AW: {ml_aw_str} "
                f"(target <1.0, elite <0.5)\n"
                f"  Profit Factor: {perf.get('profit_factor', 0)} "
                f"(target >1.75)\n"
                f"  Duration Ratio: {dur_str} "
                f"(target >2.0 - extend winners, cut losers)\n"
                f"  Max Single Loss: ${perf.get('max_single_loss', 0):,.2f}\n"
                f"  Avg Win: ${perf.get('avg_win', 0):,.2f} | "
                f"Avg Loss: ${perf.get('avg_loss', 0):,.2f}\n"
                f"  Dominant Direction: {perf.get('dominant_direction', 'NONE')} "
                f"({perf.get('bias_pct', 0)}% of profit - target >80%)\n"
                f"  Monthly Trades: {perf.get('monthly_trades', 0)} "
                f"(ideal 3-15, hard cap 20)"
            )

        challenge_str = (
            f"Challenge: {cs.get('challenge_type', 'unknown').upper()}{phase_label}\n"
            f"Account Size: ${cs.get('account_size', 0):,.0f}\n"
            f"Current Balance: ${cs.get('balance', 0):,.2f}\n"
            f"Total P/L: ${cs.get('total_pnl', 0):+,.2f}\n"
            f"Target: ${cs.get('target_balance', 0):,.0f} "
            f"(+{cs.get('profit_target_pct', 0)}%)\n"
            f"Progress: [{bar}] {progress:.1f}%\n"
            f"Remaining: ${cs.get('remaining_to_target', 0):,.2f} "
            f"(~{cs.get('est_trades_to_target', '?')} trades at current risk)\n"
            f"\n"
            f"Drawdown Room: ${cs.get('drawdown_room_remaining', 0):,.0f} remaining "
            f"of ${cs.get('firm_max_drawdown', 0):,.0f} ({cs.get('drawdown_type', 'fixed')})\n"
            f"Daily P/L: ${cs.get('daily_pnl', 0):+,.2f} "
            f"(cap: -${cs.get('personal_daily_cap', 0):,.0f}, "
            f"firm limit: -${cs.get('firm_daily_limit', 0):,.0f})\n"
            f"Daily Loss Room: ${cs.get('daily_loss_room', 0):,.0f}\n"
            f"\n"
            f"Trades Today: {cs.get('trades_today', 0)}/{cs.get('max_trades_today', 3)} "
            f"| Losses Today: {cs.get('losses_today', 0)}/3\n"
            f"Trading Days: {cs.get('trading_days', 0)}"
            f" (min required: {cs.get('min_trading_days', 0)})\n"
            f"Consecutive Losses: {cs.get('consecutive_losses', 0)}\n"
            f"\n"
            f"Current Risk: {cs.get('current_risk_pct', 0.5)}% "
            f"(${cs.get('risk_per_trade_usd', 0):,.2f} per trade)"
            f"{perf_str}"
            f"{warning_str}"
        )
    else:
        challenge_str = "Mode: STANDARD (no challenge rules active)"
        cs = challenge_status

    # Extract values for template
    risk_pct = cs.get("current_risk_pct", 0.5)
    risk_usd = cs.get("risk_per_trade_usd", 250)
    min_rr = cs.get("min_rr_ratio", 1.5)
    max_sl = cs.get("max_sl_pips", 30)
    min_sl = cs.get("min_sl_pips", 5)
    max_spread = cs.get("max_spread_pips", 2.0)
    firm_daily = cs.get("firm_daily_limit", 1250)
    firm_dd = cs.get("firm_max_drawdown", 2500)
    personal_cap = cs.get("personal_daily_cap", 625)
    max_trades = cs.get("max_trades_today", 3)
    max_consec = 2  # hardcoded personal rule
    weekend = cs.get("weekend_holding_allowed", False)

    # Compute display values
    account_size = cs.get("account_size", 50000)
    firm_daily_pct = round(firm_daily / account_size * 100, 1) if account_size else 2.5
    firm_dd_pct = round(firm_dd / account_size * 100, 1) if account_size else 5.0
    dd_type = cs.get("drawdown_type", "fixed")
    weekend_rule = "" if weekend else "\n- Close ALL positions before Friday market close"

    # Reduced risk % for after-loss
    reduced_risk_pct = max(0.25, risk_pct * 0.5)
    max_risk_pct = 1.0

    return agent_system_prompt_forex.format(
        session_id=session_id,
        signature=signature,
        forex_pairs=", ".join(forex_symbols),
        positions=today_init_position,
        challenge_status=challenge_str,
        risk_pct=risk_pct,
        risk_per_trade=f"{risk_usd:,.2f}",
        max_risk_pct=max_risk_pct,
        reduced_risk_pct=reduced_risk_pct,
        min_rr=min_rr,
        max_sl=max_sl,
        min_sl=min_sl,
        max_spread=max_spread,
        breakeven_rr=1.0,
        firm_daily_limit=f"{firm_daily:,.0f}",
        firm_daily_pct=firm_daily_pct,
        firm_max_dd=f"{firm_dd:,.0f}",
        firm_dd_pct=firm_dd_pct,
        dd_type=dd_type,
        personal_daily_cap=f"{personal_cap:,.0f}",
        max_trades=max_trades,
        max_consec_losses=max_consec,
        weekend_rule=weekend_rule,
        STOP_SIGNAL=STOP_SIGNAL,
    )


if __name__ == "__main__":
    # Test with Express 50k defaults
    print(get_agent_system_prompt_forex(
        session_id="2026-01-15_14-30-00",
        signature="test-agent",
        challenge_status={
            "mode": "challenge",
            "challenge_type": "express",
            "phase": 1,
            "account_size": 50000,
            "balance": 50000.0,
            "target_balance": 56250.0,
            "profit_target": 6250.0,
            "profit_target_pct": 12.5,
            "total_pnl": 0.0,
            "progress_pct": 0.0,
            "remaining_to_target": 6250.0,
            "est_trades_to_target": 34,
            "peak_balance": 50000.0,
            "drawdown_used": 0.0,
            "drawdown_room_remaining": 2500.0,
            "drawdown_type": "fixed",
            "firm_daily_limit": 1250.0,
            "firm_max_drawdown": 2500.0,
            "daily_pnl": 0.0,
            "daily_loss_room": 625.0,
            "personal_daily_cap": 625.0,
            "trades_today": 0,
            "max_trades_today": 3,
            "consecutive_losses": 0,
            "trading_days": 0,
            "min_trading_days": 10,
            "current_risk_pct": 0.5,
            "risk_per_trade_usd": 250.0,
            "min_rr_ratio": 1.5,
            "max_sl_pips": 30,
            "min_sl_pips": 5,
            "max_spread_pips": 2.0,
            "should_stop": False,
            "stop_reason": "",
            "is_passed": False,
            "weekend_holding_allowed": False,
        },
    ))
