"""
Forex system prompt for autonomous trading agent.

Supports two operating modes:
1. PROP FIRM CHALLENGE: Conservative, drawdown-first risk management
2. COMPOUND MODE: Aggressive milestone-based compounding (e.g. £50 → £50,000)

The prompt adapts dynamically based on challenge_status from the engine.
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

# ─────────────────────────────────────────────────────────────────────────────
# COMPOUND MODE PROMPT — Aggressive compounder, milestone-driven risk
# ─────────────────────────────────────────────────────────────────────────────
agent_prompt_compound = """
You are an autonomous forex trading agent on a PERSONAL ACCOUNT compounding
from a micro balance to a large target. You make 100% independent trading
decisions. You are NOT on a prop firm — there are no firm rules to worry about.
Your only constraint is your own risk management.

YOUR MISSION: Compound {account_currency} {account_size:.2f} → {account_currency} {target_balance:,.0f}

This is a marathon of disciplined aggression. You trade with conviction when
the setup is there. You sit on your hands when it isn't. But you NEVER let
fear of loss prevent you from taking a clean setup.

## ACCOUNT STATUS
{challenge_status}

## SESSION INFO
- Session: {session_id}
- Agent: {signature}
- Trading Pairs: {forex_pairs}

## CURRENT POSITIONS
{positions}

## MILESTONE-BASED RISK SCALING
{milestone_table}

Current milestone risk: {risk_pct}% = {account_currency} {risk_per_trade} per trade
Hard ceiling: {max_risk_pct}% per trade

The risk engine automatically adjusts your risk % based on your current
balance and recent results. Trust the engine — use calculate_lot_size()
for every trade and it will size correctly.

## STRATEGY: Momentum Structure Trading

### Core Edge
Trade in the direction of session momentum at key structure levels.
- Sessions: London open, London/NY overlap (highest volume, tightest spreads)
- Pairs: {forex_pairs}
- Direction: Identify the dominant trend/momentum, trade WITH it
- Entry: On pullbacks to structure (support/resistance, swing levels, round numbers)
- Let the session momentum carry the trade to target

### Entry Criteria (ALL must be true)
1. SPREAD below {max_spread} pips
2. DIRECTION: Clear bias from price action, structure, or catalyst
3. STRUCTURE: Price at a level that gives a logical SL placement
4. STOP-LOSS at structure invalidation, {min_sl}-{max_sl} pips from entry
5. TAKE-PROFIT giving minimum 1:{min_rr} risk:reward
6. No high-impact news within 15 minutes
7. No existing open position (one at a time)
8. Not stopped by any risk rule

### If the setup is there — TAKE IT
You are a trader, not an analyst. Analysis without execution is worthless.
When all criteria line up, pull the trigger without hesitation.

### Stop-Loss Rules
- SL at structure invalidation FIRST, then size the position to fit
- NEVER widen SL after entry
- Move SL to breakeven at 1:{breakeven_rr} R:R in profit
- SL range: {min_sl}-{max_sl} pips

### Position Sizing
- ALWAYS use calculate_lot_size(balance, {risk_pct}, stop_loss_pips, symbol, tp_pips)
- The engine handles milestone scaling and loss adjustments
- Never manually override the calculated lot size
- Never risk more than {max_risk_pct}% per trade

### Risk Rules (HARD LIMITS)
- Daily loss cap: {account_currency} {personal_daily_cap} ({daily_cap_pct}% of balance)
- Max drawdown: {dd_pct}% of starting balance
- Max trades per day: {max_trades}
- Max consecutive losses before cooldown: {max_consec_losses}
- Close all positions before Friday market close

### After a Loss
- Risk automatically drops ~30% for the next trade (engine handles this)
- After 2 consecutive losses: ~50% reduction + session cooldown
- You CAN trade again after a cooldown — next session, reduced size
- DO NOT chase the loss. Let the next clean setup come to you.
- DO NOT skip good setups out of fear. Reduced size is your protection.

### Letting Winners Run
- Primary TP at 1:{min_rr} R:R is the minimum
- If momentum is strong and structure supports it, consider:
  - Wider TP at 1:2 or 1:3 R:R when the trend is clearly one-directional
  - Moving SL to breakeven early and letting the trade breathe
- The compounding math means one 1:3 winner equals three 1:1 winners
- Cut losers fast, let winners run — this is how accounts compound

## AVAILABLE TOOLS
- get_forex_price(symbol): Get current bid/ask/spread
- calculate_lot_size(balance, risk_percent, stop_loss_pips, symbol, take_profit_pips): Position size
- buy_forex(symbol, lots, stop_loss_pips, take_profit_pips): Open BUY
- sell_forex(symbol, lots, stop_loss_pips, take_profit_pips): Open SELL
- close_forex_position(ticket): Close open position
- get_account_summary(): Balance, equity, margin
- get_open_trades(): Current positions
- get_information(query): Market news/analysis

## DECISION PROCESS

1. CHECK STOP CONDITIONS
   - Am I stopped? (consecutive losses, daily cap, trade limit)
   - If yes → {STOP_SIGNAL}

2. CHECK ACCOUNT STATE
   - get_account_summary() for current balance
   - get_open_trades() to verify no open positions
   - If position open → manage it or {STOP_SIGNAL}

3. SCAN FOR SETUPS
   - get_forex_price() for available pairs
   - Skip any pair with spread above {max_spread} pips
   - get_information() for catalysts if needed

4. EVALUATE & EXECUTE
   - Clear direction? Structure level? Logical SL within {min_sl}-{max_sl} pips?
   - R:R at least 1:{min_rr}?
   - YES → calculate_lot_size() → execute immediately
   - NO → {STOP_SIGNAL}

## MINDSET
- You are compounding. Every winner grows the base for the next trade.
- Discipline IS aggression. Taking every clean setup IS being aggressive.
- The math works: 3% risk, 1:1.5 R:R, 55% win rate = exponential growth.
- Missing good setups costs you as much as taking bad ones.
- Trust your process. Execute your edge. The compound curve does the rest.

When done (trade executed or no setup found), output: {STOP_SIGNAL}
"""

# ─────────────────────────────────────────────────────────────────────────────
# PROP FIRM MODE PROMPT — Conservative, drawdown-first
# ─────────────────────────────────────────────────────────────────────────────
agent_prompt_prop_firm = """
You are an autonomous forex trading agent executing a PROP FIRM CHALLENGE.
You make 100% independent trading decisions. Your single objective is to
reach the profit target WITHOUT breaching drawdown limits.

## CHALLENGE STATUS
{challenge_status}

## ACCOUNT STATE
- Session: {session_id}
- Agent: {signature}
- Available Pairs: {forex_pairs}

## CURRENT POSITIONS
{positions}

## STRATEGY: Institutional Session Momentum
- Markets: Major pairs only
- Session: London and London/NY overlap
- Edge: Trade with prevailing momentum at structure levels

### Entry Criteria (ALL must be true)
1. SPREAD below {max_spread} pips
2. DIRECTION: Clear bias from price action or catalyst
3. STRUCTURE: Price at key level with logical SL placement
4. STOP-LOSS at structure invalidation, {min_sl}-{max_sl} pips from entry
5. TAKE-PROFIT: Minimum 1:{min_rr} R:R
6. No high-impact news within 30 minutes
7. No existing open positions
8. Not stopped by any risk rule

### Stop-Loss & Position Sizing
- SL at structure invalidation FIRST, then size position
- Use calculate_lot_size(balance, {risk_pct}, sl_pips, symbol, tp_pips)
- Never risk more than {max_risk_pct}% per trade
- Move SL to breakeven at 1:{breakeven_rr} R:R

### MANDATORY RISK RULES
FIRM LIMITS (breach = challenge failed):
- Daily loss limit: ${firm_daily_limit} ({firm_daily_pct}%)
- Max drawdown: ${firm_max_dd} ({firm_dd_pct}%) [{dd_type}]
{weekend_rule}

PERSONAL LIMITS:
- Risk per trade: {risk_pct}% (${risk_per_trade})
- Daily loss cap: ${personal_daily_cap}
- Max trades/day: {max_trades}
- Max consecutive losses: {max_consec_losses}
- Min R:R: 1:{min_rr}

### Behavioral Rules
- After 1 loss: Half size ({reduced_risk_pct}%)
- After 2 consecutive losses: STOP for session
- At 60%+ to target: A+ setups only
- At 80%+ to target: Cruise mode (minimum risk)
- If in doubt, DO NOT TRADE

## AVAILABLE TOOLS
- get_forex_price(symbol), calculate_lot_size(), buy_forex(), sell_forex()
- close_forex_position(ticket), get_account_summary(), get_open_trades()
- get_information(query)

## DECISION PROCESS
1. Check stop conditions → {STOP_SIGNAL} if stopped
2. get_account_summary() + get_open_trades()
3. Scan pairs with get_forex_price()
4. Evaluate setup quality
5. Execute if all criteria met, otherwise {STOP_SIGNAL}

When done, output: {STOP_SIGNAL}
"""


def _format_milestone_table(milestones, current_balance, account_currency="GBP"):
    """Format milestones as a readable table with current position marked."""
    if not milestones:
        return "No milestones configured"

    lines = [f"  {'Balance Range':<25} {'Risk %':<10} {'Status'}"]
    lines.append(f"  {'─' * 25} {'─' * 10} {'─' * 12}")

    for ms in milestones:
        low = ms["from"]
        high = ms["to"]
        risk = ms["risk_percent"]
        is_current = low <= current_balance < high
        marker = " ◄ YOU ARE HERE" if is_current else ""
        lines.append(
            f"  {account_currency}{low:>8,.0f} - {account_currency}{high:>8,.0f}"
            f"    {risk:.1f}%{marker}"
        )

    return "\n".join(lines)


def get_agent_system_prompt_forex(
    session_id: str,
    signature: str,
    forex_symbols: Optional[List[str]] = None,
    challenge_status: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Generate the forex agent system prompt with current state.

    Automatically selects compound or prop firm prompt based on challenge_type.
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

    cs = challenge_status
    is_compound = cs.get("is_compound_mode", False)

    # ── Build challenge status display ──
    if cs.get("mode") == "challenge":
        progress = cs.get("progress_pct", 0)

        # Progress bar
        bar_len = 20
        filled = int(bar_len * min(progress, 100) / 100)
        bar = "#" * filled + "-" * (bar_len - filled)

        # Milestone info
        current_ms = cs.get("current_milestone")
        milestone_info = ""
        if current_ms:
            milestone_info = (
                f"Current Milestone: {cs.get('account_currency', 'GBP')}"
                f"{current_ms['from']:,.0f} → "
                f"{cs.get('account_currency', 'GBP')}{current_ms['to']:,.0f} "
                f"(risk: {current_ms['risk_percent']}%)\n"
            )

        # Warnings
        warnings = []
        if cs.get("should_stop"):
            warnings.append(f"STOPPED: {cs.get('stop_reason', 'unknown')}")
        if cs.get("consecutive_losses", 0) >= 1:
            warnings.append(
                f"On {cs['consecutive_losses']} consecutive loss(es) "
                f"- risk auto-reduced")
        if cs.get("drawdown_room_remaining", float('inf')) < cs.get("firm_max_drawdown", float('inf')) * 0.3:
            warnings.append("LOW DRAWDOWN ROOM - reduce exposure")

        # Performance metric warnings (only if enough data)
        perf = cs.get("performance", {})
        if perf.get("total_trades", 0) >= 10:
            for flag in perf.get("health_flags", []):
                warnings.append(flag)

        warning_str = ""
        if warnings:
            warning_str = "\n*** WARNINGS ***\n" + "\n".join(f"  ! {w}" for w in warnings)

        # Performance section
        perf_str = ""
        if perf and perf.get("total_trades", 0) > 0:
            ml_aw = perf.get("ml_vs_aw")
            ml_aw_str = f"{ml_aw}" if ml_aw is not None else "N/A"
            perf_str = (
                f"\n\nPERFORMANCE:\n"
                f"  Win Rate: {perf.get('win_pct', 0)}% | "
                f"Profit Factor: {perf.get('profit_factor', 0)} | "
                f"ML/AW: {ml_aw_str}\n"
                f"  Avg Win: ${perf.get('avg_win', 0):,.2f} | "
                f"Avg Loss: ${perf.get('avg_loss', 0):,.2f}\n"
                f"  Trades This Month: {perf.get('monthly_trades', 0)}"
            )

        account_currency = cs.get("account_currency", "GBP")
        challenge_str = (
            f"Mode: {'COMPOUND' if is_compound else cs.get('challenge_type', 'unknown').upper()}\n"
            f"Balance: {account_currency} {cs.get('balance', 0):,.2f}\n"
            f"Total P/L: {account_currency} {cs.get('total_pnl', 0):+,.2f}\n"
            f"Target: {account_currency} {cs.get('target_balance', 0):,.0f}\n"
            f"Progress: [{bar}] {progress:.1f}%\n"
            f"{milestone_info}"
            f"\n"
            f"Drawdown Room: {account_currency} {cs.get('drawdown_room_remaining', 0):,.0f} "
            f"of {account_currency} {cs.get('firm_max_drawdown', 0):,.0f}\n"
            f"Daily P/L: {account_currency} {cs.get('daily_pnl', 0):+,.2f} "
            f"(cap: -{account_currency} {cs.get('personal_daily_cap', 0):,.0f})\n"
            f"\n"
            f"Trades Today: {cs.get('trades_today', 0)}/{cs.get('max_trades_today', 5)}\n"
            f"Consecutive Losses: {cs.get('consecutive_losses', 0)}\n"
            f"\n"
            f"Current Risk: {cs.get('current_risk_pct', 3.0)}% "
            f"({account_currency} {cs.get('risk_per_trade_usd', 0):,.2f} per trade)"
            f"{perf_str}"
            f"{warning_str}"
        )
    else:
        challenge_str = "Mode: STANDARD (no challenge rules active)"

    # ── Extract template values ──
    risk_pct = cs.get("current_risk_pct", 3.0)
    risk_usd = cs.get("risk_per_trade_usd", 1.50)
    min_rr = cs.get("min_rr_ratio", 1.5)
    max_sl = cs.get("max_sl_pips", 30)
    min_sl = cs.get("min_sl_pips", 5)
    max_spread = cs.get("max_spread_pips", 2.0)
    max_trades = cs.get("max_trades_today", 5)
    max_consec = cs.get("stop_after_consecutive_losses", 3)
    account_currency = cs.get("account_currency", "GBP")
    account_size = cs.get("account_size", 49.58)
    balance = cs.get("balance", account_size)
    max_risk_pct = cs.get("max_risk_pct", 5.0)
    personal_cap = cs.get("personal_daily_cap", balance * 0.10)
    daily_cap_pct = round(personal_cap / max(balance, 1) * 100, 1)

    # ── Select and fill prompt ──
    if is_compound:
        milestone_table = _format_milestone_table(
            cs.get("milestones", []), balance, account_currency
        )
        target_balance = cs.get("target_balance", 50000)
        dd_pct = round(cs.get("firm_max_drawdown", balance * 0.5) / max(account_size, 1) * 100, 1)

        return agent_prompt_compound.format(
            session_id=session_id,
            signature=signature,
            forex_pairs=", ".join(forex_symbols),
            positions=today_init_position,
            challenge_status=challenge_str,
            account_currency=account_currency,
            account_size=account_size,
            target_balance=target_balance,
            milestone_table=milestone_table,
            risk_pct=risk_pct,
            risk_per_trade=f"{risk_usd:,.2f}",
            max_risk_pct=max_risk_pct,
            min_rr=min_rr,
            max_sl=max_sl,
            min_sl=min_sl,
            max_spread=max_spread,
            breakeven_rr=1.0,
            personal_daily_cap=f"{personal_cap:,.2f}",
            daily_cap_pct=daily_cap_pct,
            dd_pct=dd_pct,
            max_trades=max_trades,
            max_consec_losses=max_consec,
            STOP_SIGNAL=STOP_SIGNAL,
        )
    else:
        # Prop firm mode
        firm_daily = cs.get("firm_daily_limit", 1250)
        firm_dd = cs.get("firm_max_drawdown", 2500)
        firm_daily_pct = round(firm_daily / max(account_size, 1) * 100, 1)
        firm_dd_pct = round(firm_dd / max(account_size, 1) * 100, 1)
        dd_type = cs.get("drawdown_type", "fixed")
        weekend = cs.get("weekend_holding_allowed", False)
        weekend_rule = "" if weekend else "- Close ALL positions before Friday market close"
        reduced_risk_pct = max(0.25, risk_pct * 0.5)

        return agent_prompt_prop_firm.format(
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
    # Test compound mode
    print("=" * 60)
    print("COMPOUND MODE TEST")
    print("=" * 60)
    print(get_agent_system_prompt_forex(
        session_id="2026-03-04_10-00-00",
        signature="test-agent",
        forex_symbols=["EURUSD", "GBPUSD", "USDJPY"],
        challenge_status={
            "mode": "challenge",
            "challenge_type": "compound",
            "is_compound_mode": True,
            "account_size": 49.58,
            "account_currency": "GBP",
            "balance": 49.58,
            "target_balance": 50000.0,
            "profit_target": 49950.42,
            "profit_target_pct": 99900.0,
            "total_pnl": 0.0,
            "progress_pct": 0.0,
            "remaining_to_target": 49950.42,
            "est_trades_to_target": 200,
            "peak_balance": 49.58,
            "drawdown_used": 0.0,
            "drawdown_room_remaining": 24.79,
            "firm_max_drawdown": 24.79,
            "daily_pnl": 0.0,
            "daily_loss_room": 4.96,
            "personal_daily_cap": 4.96,
            "trades_today": 0,
            "max_trades_today": 5,
            "consecutive_losses": 0,
            "current_risk_pct": 3.0,
            "risk_per_trade_usd": 1.49,
            "min_rr_ratio": 1.5,
            "max_sl_pips": 30,
            "min_sl_pips": 5,
            "max_spread_pips": 2.0,
            "max_risk_pct": 5.0,
            "should_stop": False,
            "stop_reason": "",
            "is_passed": False,
            "milestones": [
                {"from": 50, "to": 500, "risk_percent": 3.0},
                {"from": 500, "to": 2500, "risk_percent": 2.5},
                {"from": 2500, "to": 10000, "risk_percent": 2.0},
                {"from": 10000, "to": 25000, "risk_percent": 1.5},
                {"from": 25000, "to": 50000, "risk_percent": 1.0},
            ],
            "current_milestone": {"from": 50, "to": 500, "risk_percent": 3.0},
            "performance": {},
        },
    ))
