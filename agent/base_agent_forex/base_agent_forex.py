"""
BaseAgentForex class - Autonomous forex trading agent.

Supports two modes:
1. PROP FIRM CHALLENGE: Conservative risk, pass the evaluation
2. COMPOUND MODE: Aggressive compounding from micro to target (e.g. £50 → £50k)

In compound mode, risk scales dynamically with balance milestones defined in
the challenge config. Early phases are aggressive (3-5%) to build capital fast;
later phases taper down (1-1.5%) to protect compounded gains.

Trading backends:
- mt5_native: Direct MetaTrader5 IPC (Windows, lowest latency)
- metaapi: Cloud relay (any OS, ~100ms latency)
- browser: Playwright automation of FundedNext web trader
- simulation: Local simulation for testing (no real execution)
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import AIMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from agent.model_factory import create_llm_model, is_anthropic_model


from prompts.agent_prompt_forex import STOP_SIGNAL, get_agent_system_prompt_forex
from tools.general_tools import (extract_conversation, extract_tool_messages,
                                 get_config_value, write_config_value)
from tools.price_tools import add_no_trade_record


load_dotenv()


class BaseAgentForex:
    """
    Autonomous forex trading agent supporting prop firm and compound modes.

    In compound mode, risk is milestone-driven: aggressive at small balances
    to build capital, tapering as the account grows to protect gains.
    """

    MAJOR_PAIRS = [
        "EURUSD", "GBPUSD", "USDJPY", "USDCHF",
        "AUDUSD", "NZDUSD", "USDCAD",
    ]

    MINOR_PAIRS = [
        "EURGBP", "EURJPY", "EURCHF", "GBPJPY",
        "GBPCHF", "AUDJPY", "NZDJPY", "AUDNZD",
    ]

    DEFAULT_FOREX_SYMBOLS = MAJOR_PAIRS

    PIP_VALUES = {
        "EURUSD": 10.0, "GBPUSD": 10.0, "AUDUSD": 10.0,
        "NZDUSD": 10.0, "USDCHF": 10.0, "USDCAD": 10.0,
        "USDJPY": 6.67, "EURGBP": 12.50, "EURJPY": 6.67,
        "EURCHF": 10.0, "GBPJPY": 6.67, "GBPCHF": 10.0,
        "AUDJPY": 6.67, "NZDJPY": 6.67, "AUDNZD": 6.50,
    }

    def __init__(
        self,
        signature: str,
        basemodel: str,
        forex_symbols: Optional[List[str]] = None,
        mcp_config: Optional[Dict[str, Dict[str, Any]]] = None,
        log_path: Optional[str] = None,
        max_steps: int = 50,
        max_retries: int = 3,
        base_delay: float = 2.0,
        openai_base_url: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        initial_cash: float = 50000.0,
        init_date: str = "2026-01-01",
        market: str = "forex",
        # Full challenge config dict from JSON
        challenge_config: Optional[Dict[str, Any]] = None,
        # MT4/MT5 connection params
        mt4_mt5_config: Optional[Dict[str, Any]] = None,
        # Trading session control
        trading_sessions: Optional[List[str]] = None,
        loop_interval_seconds: int = 300,
        # Legacy params kept for backwards compat with main.py
        challenge_mode: bool = True,
        risk_percent: float = 0.5,
        target_pips: float = 20.0,
        target_balance: float = 56250.0,
        max_daily_loss_percent: float = 2.5,
        max_drawdown_percent: float = 5.0,
    ):
        self.signature = signature
        self.basemodel = basemodel
        self.market = "forex"

        self.forex_symbols = forex_symbols or self.DEFAULT_FOREX_SYMBOLS

        self.max_steps = max_steps
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.initial_cash = initial_cash
        self.init_date = init_date

        self.mcp_config = mcp_config or self._get_default_mcp_config()
        self.base_log_path = log_path or "./data/agent_data_forex"

        self.openai_base_url = openai_base_url or os.getenv("OPENAI_API_BASE")
        # For Anthropic models, prefer ANTHROPIC_API_KEY
        if is_anthropic_model(basemodel):
            self.openai_api_key = openai_api_key or os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY")
        else:
            self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")

        self.mt4_mt5_config = mt4_mt5_config or {}
        self.loop_interval_seconds = loop_interval_seconds

        # ── Challenge Configuration ──────────────────────────────────
        self.challenge_config = challenge_config or {}
        self.challenge_mode = self.challenge_config.get("enabled", challenge_mode)
        self.challenge_type = self.challenge_config.get("challenge_type", "express")

        # Load firm rules for the selected challenge type
        firm_rules = self.challenge_config.get("firm_rules", {})
        self.firm = firm_rules.get(self.challenge_type, {})

        # Load personal rules (our own tighter guardrails)
        self.personal = self.challenge_config.get("personal_rules", {})

        # Load behavioral rules
        self.behavioral = self.challenge_config.get("behavioral_rules", {})

        # Load compound milestones (for milestone-based risk scaling)
        self.milestones = self._parse_milestones(
            self.challenge_config.get("milestones", {})
        )
        self.is_compound_mode = self.challenge_type == "compound"

        # Account size from config
        account_size = self.challenge_config.get("account_size", initial_cash)
        self.account_size = account_size
        self.initial_cash = account_size

        # ── Derive concrete limits from firm + personal rules ────────

        # Firm limits (hard limits we must never breach)
        self.firm_daily_loss_pct = self.firm.get(
            "firm_max_daily_loss_percent", max_daily_loss_percent)
        self.firm_max_dd_pct = self.firm.get(
            "firm_max_total_drawdown_percent", max_drawdown_percent)
        self.firm_daily_loss_limit = self._pct_to_amount(self.firm_daily_loss_pct)
        self.firm_max_drawdown = self._pct_to_amount(self.firm_max_dd_pct)
        self.drawdown_type = self.firm.get("drawdown_type", "fixed")
        self.min_trading_days = self.firm.get(
            "min_trading_days", self.firm.get("min_trading_days_per_phase", 10))
        self.weekend_holding_allowed = self.firm.get("weekend_holding_allowed", False)

        # Profit target — use explicit target_balance from config if provided
        explicit_target = self.challenge_config.get("target_balance")
        profit_target_pct = self.firm.get("profit_target_percent")
        if profit_target_pct is None:
            phase_1 = self.firm.get("phase_1_target_percent", 8.0)
            profit_target_pct = phase_1
        self.profit_target_pct = profit_target_pct

        if explicit_target is not None:
            self.target_balance = float(explicit_target)
            self.profit_target = self.target_balance - self.account_size
        else:
            self.profit_target = self.account_size * (profit_target_pct / 100)
            self.target_balance = self.account_size + self.profit_target

        # Personal limits (our tighter guardrails)
        daily_cap_ratio = self.personal.get("personal_daily_loss_cap_ratio", 0.5)
        self.personal_daily_loss_cap = self.firm_daily_loss_limit * daily_cap_ratio
        self.risk_percent = self.personal.get("risk_percent_per_trade", risk_percent)
        self.max_risk_percent = self.personal.get("max_risk_percent_per_trade", 1.0)
        self.reduced_risk_percent = self.personal.get("reduced_risk_percent", 0.25)
        self.reduce_size_at_pct = self.personal.get("reduce_size_at_target_percent", 60)
        self.min_rr_ratio = self.personal.get("min_risk_reward_ratio", 1.5)
        self.max_trades_per_day = self.personal.get(
            "max_trades_per_day", 5 if self.is_compound_mode else 3)
        self.max_concurrent_trades = self.personal.get("max_concurrent_trades", 1)
        self.stop_after_consecutive_losses = self.personal.get(
            "stop_trading_after_consecutive_losses", 3 if self.is_compound_mode else 2)
        self.max_spread_pips = self.personal.get("max_spread_pips", 2.0)
        self.max_sl_pips = self.personal.get("max_sl_pips", 30)
        self.min_sl_pips = self.personal.get("min_sl_pips", 5)
        self.breakeven_at_rr = self.personal.get("move_sl_to_breakeven_at_rr", 1.0)

        # Trading sessions
        self.trading_sessions = (
            self.personal.get("trading_sessions")
            or trading_sessions
            or ["london_ny_overlap"]
        )

        # ── Runtime State Tracking ───────────────────────────────────
        self.current_balance = self.account_size
        self.daily_starting_balance = self.account_size
        self.peak_balance = self.account_size
        self.trades_today = 0
        self.losses_today = 0
        self.consecutive_losses = 0
        self.total_trading_days = 0
        self.current_phase = 1  # For 2-step challenges
        self.daily_pnl = 0.0
        self.total_pnl = 0.0
        self.session_stopped = False

        # ── Performance Metrics Tracking ─────────────────────────────
        # Trade log: list of dicts with pnl, direction, symbol, weekday, duration
        self.trade_log: List[Dict[str, Any]] = []
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_win_pnl = 0.0
        self.total_loss_pnl = 0.0
        self.max_single_loss = 0.0
        self.total_win_duration_mins = 0.0
        self.total_loss_duration_mins = 0.0
        # Directional tracking
        self.long_profit = 0.0
        self.short_profit = 0.0
        # Per-weekday tracking {0=Mon..4=Fri: {"trades": n, "pnl": x}}
        self.weekday_stats: Dict[int, Dict[str, float]] = {
            i: {"trades": 0, "pnl": 0.0} for i in range(5)
        }
        # Per-symbol tracking
        self.symbol_stats: Dict[str, Dict[str, float]] = {}
        # Monthly trade count
        self.monthly_trades = 0
        self.current_month = None

        # Internal components
        self.client: Optional[MultiServerMCPClient] = None
        self.tools: Optional[List] = None
        self.model: Optional[ChatOpenAI] = None
        self.agent: Optional[Any] = None

        self.data_path = os.path.join(self.base_log_path, self.signature)
        self.position_file = os.path.join(self.data_path, "position", "position.jsonl")

    def _pct_to_amount(self, pct) -> float:
        """Convert a percentage to a dollar amount based on account size."""
        if pct is None:
            return float('inf')
        return self.account_size * (float(pct) / 100)

    def _get_current_milestone(self, balance: float) -> Optional[Dict[str, Any]]:
        """Return the milestone dict for the current balance, or None."""
        for ms in self.milestones:
            if ms["from"] <= balance < ms["to"]:
                return ms
        if self.milestones and balance >= self.milestones[-1]["to"]:
            return self.milestones[-1]
        return None

    @staticmethod
    def _parse_milestones(milestones_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse milestone config into sorted list of {from, to, risk_percent}."""
        parsed = []
        for key, val in milestones_dict.items():
            if key.startswith("_"):
                continue
            if isinstance(val, dict) and "from" in val and "to" in val:
                parsed.append({
                    "from": float(val["from"]),
                    "to": float(val["to"]),
                    "risk_percent": float(val.get("risk_percent", 3.0)),
                })
        parsed.sort(key=lambda m: m["from"])
        return parsed

    def _get_default_mcp_config(self) -> Dict[str, Dict[str, Any]]:
        return {
            "math": {
                "transport": "streamable_http",
                "url": f"http://localhost:{os.getenv('MATH_HTTP_PORT', '8000')}/mcp",
            },
            "search": {
                "transport": "streamable_http",
                "url": f"http://localhost:{os.getenv('SEARCH_HTTP_PORT', '8001')}/mcp",
            },
            "forex_trade": {
                "transport": "streamable_http",
                "url": f"http://localhost:{os.getenv('FOREX_HTTP_PORT', '8006')}/mcp",
            },
        }

    async def initialize(self) -> None:
        """Initialize MCP client and AI model."""
        print(f"Initializing forex agent: {self.signature}")
        print(f"Mode: {'CHALLENGE' if self.challenge_mode else 'STANDARD'}")
        ccy = self.challenge_config.get("account_currency", "$")
        if self.challenge_mode:
            print(f"Challenge type: {self.challenge_type.upper()}")
            desc = self.firm.get("description", "")
            if desc:
                print(f"  {desc}")
            print(f"Account size: {ccy}{self.account_size:,.0f}")
            print(f"Profit target: {ccy}{self.profit_target:,.0f} "
                  f"-> {ccy}{self.target_balance:,.0f}")
            print(f"Limits: {self.firm_daily_loss_pct}% daily loss "
                  f"({ccy}{self.firm_daily_loss_limit:,.0f}) / "
                  f"{self.firm_max_dd_pct}% total DD "
                  f"({ccy}{self.firm_max_drawdown:,.0f}) [{self.drawdown_type}]")
            print(f"Risk per trade: {self.risk_percent}% "
                  f"({ccy}{self.account_size * self.risk_percent / 100:,.2f})")
            print(f"Daily loss cap: {ccy}{self.personal_daily_loss_cap:,.0f} "
                  f"(50% of firm's {ccy}{self.firm_daily_loss_limit:,.0f})")
            risk_per_trade = self.account_size * self.risk_percent / 100
            if risk_per_trade > 0:
                losing_streak = int(self.firm_max_drawdown / risk_per_trade)
                print(f"Survivable losing streak: ~{losing_streak} consecutive losses "
                      f"before firm DD breach")
            print(f"Min trading days: {self.min_trading_days}")
            print(f"Min R:R ratio: 1:{self.min_rr_ratio}")

        if not self.openai_api_key:
            if is_anthropic_model(self.basemodel):
                raise ValueError(
                    "Anthropic API key not set. Configure ANTHROPIC_API_KEY in .env file."
                )
            else:
                raise ValueError(
                    "API key not set. Configure OPENAI_API_KEY (or ANTHROPIC_API_KEY for Claude) in .env file."
                )

        try:
            self.client = MultiServerMCPClient(self.mcp_config)
            self.tools = await self.client.get_tools()
            if not self.tools:
                print("Warning: No MCP tools loaded. "
                      "Ensure forex MCP services are running.")
            else:
                print(f"Loaded {len(self.tools)} MCP tools")
        except Exception as e:
            raise RuntimeError(
                f"Failed to initialize MCP client: {e}\n"
                f"Ensure MCP services are running: "
                f"python agent_tools/start_mcp_services.py"
            )

        try:
            # Create AI model using model factory (auto-detects Anthropic, DeepSeek, OpenAI)
            self.model = create_llm_model(
                basemodel=self.basemodel,
                openai_base_url=self.openai_base_url,
                openai_api_key=self.openai_api_key,
                max_retries=3,
                timeout=60,
            )
        except Exception as e:
            raise RuntimeError(f"Failed to initialize AI model: {e}")

        print(f"Forex Agent {self.signature} initialization completed")

    # ── Risk Management ──────────────────────────────────────────────

    def get_current_risk_percent(self) -> float:
        """
        Adaptive risk sizing based on balance milestones and recent results.

        COMPOUND MODE (milestone-driven):
          Uses milestones from config to scale risk with account size.
          After a loss: drops one milestone tier (not to unusable levels).
          Minimum risk is floored so 0.01 lot is still openable.

        PROP FIRM MODE (progress-driven):
          60%+ to target: reduced risk
          80%+ to target: cruise mode
          After a loss: half size
        """
        if not self.challenge_mode:
            return self.risk_percent

        # ── Compound mode: milestone-based scaling ──
        if self.is_compound_mode and self.milestones:
            bal = self.current_balance
            base_risk = self.risk_percent  # fallback

            # Find which milestone we're in
            for ms in self.milestones:
                if ms["from"] <= bal < ms["to"]:
                    base_risk = ms["risk_percent"]
                    break
            else:
                # Above all milestones — use the last (most conservative)
                if bal >= self.milestones[-1]["to"]:
                    base_risk = self.milestones[-1]["risk_percent"]
                # Below all milestones — use the first (most aggressive)
                elif bal < self.milestones[0]["from"]:
                    base_risk = self.milestones[0]["risk_percent"]

            # After a loss: step down by ~30% but floor at a usable level
            # Floor: ensure risk_amount >= $0.50 (enough for 0.01 lot with ~50 pip SL)
            if self.consecutive_losses >= 1:
                base_risk = base_risk * 0.7
            if self.consecutive_losses >= 2:
                base_risk = base_risk * 0.5

            # Absolute floor: enough to open minimum lot
            min_risk_amount = 0.50  # USD
            min_risk_pct = (min_risk_amount / max(bal, 1.0)) * 100
            base_risk = max(base_risk, min_risk_pct)

            # Hard ceiling from config
            return min(base_risk, self.max_risk_percent)

        # ── Prop firm mode: progress-based scaling ──
        progress = self.get_target_progress_pct()

        if progress >= 80:
            return max(0.15, self.reduced_risk_percent * 0.6)
        if progress >= self.reduce_size_at_pct:
            return self.reduced_risk_percent
        if self.consecutive_losses >= 1:
            return max(0.25, self.risk_percent * 0.5)

        return self.risk_percent

    def calculate_lot_size(
        self, balance: float, stop_loss_pips: float, symbol: str = "EURUSD"
    ) -> float:
        """
        Calculate lot size from balance, risk %, and stop-loss distance.

        The stop-loss goes at the market-structure invalidation point FIRST,
        then lot size is calculated to risk the correct dollar amount at
        that SL distance. Never the other way around.
        """
        risk_pct = self.get_current_risk_percent()
        risk_amount = balance * (risk_pct / 100)
        pip_value_per_lot = self.PIP_VALUES.get(symbol, 10.0)
        lot_size = risk_amount / (stop_loss_pips * pip_value_per_lot)
        lot_size = max(0.01, round(lot_size, 2))
        return lot_size

    def check_daily_loss_limit(self) -> bool:
        """Check if we hit our PERSONAL daily loss cap (tighter than firm's)."""
        if self.daily_pnl <= -self.personal_daily_loss_cap:
            return True
        return False

    def check_firm_daily_loss_limit(self) -> bool:
        """Check if approaching the FIRM's daily loss limit (70% warning)."""
        if self.firm_daily_loss_limit == float('inf'):
            return False
        return self.daily_pnl <= -(self.firm_daily_loss_limit * 0.7)

    def check_max_drawdown(self) -> bool:
        """Check if maximum drawdown has been breached."""
        if self.drawdown_type in ("trailing", "trailing_relative"):
            drawdown = self.peak_balance - self.current_balance
        else:
            drawdown = self.account_size - self.current_balance
        return drawdown >= self.firm_max_drawdown

    def check_near_max_drawdown(self) -> bool:
        """Check if within 70% of the firm's max drawdown."""
        if self.drawdown_type in ("trailing", "trailing_relative"):
            drawdown = self.peak_balance - self.current_balance
        else:
            drawdown = self.account_size - self.current_balance
        return drawdown >= (self.firm_max_drawdown * 0.7)

    def should_stop_trading_session(self) -> tuple:
        """
        Central safety check - evaluate ALL stop conditions.
        Returns (should_stop: bool, reason: str).

        Compound mode is significantly more permissive than prop firm mode
        because there are no firm drawdown rules to breach — only self-imposed
        risk management to survive variance.
        """
        if self.session_stopped:
            return True, "Session already stopped by earlier rule"

        # ── Hard limits (both modes) ──
        if self.check_max_drawdown():
            self.session_stopped = True
            return True, "CRITICAL: MAX DRAWDOWN BREACHED - STOP ALL TRADING"

        if self.check_daily_loss_limit():
            self.session_stopped = True
            return True, (
                f"Daily loss cap hit: "
                f"${abs(self.daily_pnl):,.0f} >= "
                f"${self.personal_daily_loss_cap:,.0f}")

        # ── Compound mode: permissive limits ──
        if self.is_compound_mode:
            # Allow more consecutive losses (reduced size, not full stop)
            if self.consecutive_losses >= self.stop_after_consecutive_losses:
                self.session_stopped = True
                return True, (
                    f"Consecutive losses: {self.consecutive_losses} "
                    f"(limit: {self.stop_after_consecutive_losses}) - "
                    f"cool off, next session trades at reduced size")

            if self.trades_today >= self.max_trades_per_day:
                return True, f"Max trades per day reached: {self.trades_today}"

            # Monthly cap is much higher in compound mode
            monthly_cap = self.behavioral.get("monthly_trade_cap", 60)
            if self.monthly_trades >= monthly_cap:
                return True, (
                    f"Monthly trade cap: {self.monthly_trades}/{monthly_cap}")

            # No performance-based stop in early compound phases — too few
            # trades to have meaningful statistics
            if self.current_balance > 2500 and self.total_trades >= 10:
                should_reduce, reason = self.should_reduce_exposure()
                if should_reduce and self.trades_today > 0:
                    return True, f"Metrics warning: {reason}"

            return False, ""

        # ── Prop firm mode: conservative limits ──
        if self.check_firm_daily_loss_limit():
            self.session_stopped = True
            return True, (
                f"WARNING: Approaching firm daily loss limit (70%): "
                f"${abs(self.daily_pnl):,.0f}")

        if self.check_near_max_drawdown():
            self.session_stopped = True
            return True, "Approaching firm max drawdown (70%) - stopping for safety"

        if self.consecutive_losses >= self.stop_after_consecutive_losses:
            self.session_stopped = True
            return True, (
                f"Consecutive losses: {self.consecutive_losses} "
                f"(limit: {self.stop_after_consecutive_losses})")

        if self.losses_today >= 3:
            self.session_stopped = True
            return True, (
                f"Daily losing trades cap: {self.losses_today} losses today "
                f"(max 3) - prevents revenge trading")

        if self.trades_today >= self.max_trades_per_day:
            return True, f"Max trades per day reached: {self.trades_today}"

        if self.monthly_trades >= 20:
            return True, (
                f"Monthly trade hard cap: {self.monthly_trades}/20 - "
                f"overtrading reduces payout probability")

        should_reduce, reason = self.should_reduce_exposure()
        if should_reduce and self.trades_today > 0:
            return True, f"Metrics warning: {reason}"

        return False, ""

    def update_after_trade(
        self,
        pnl: float,
        direction: str = "BUY",
        symbol: str = "EURUSD",
        duration_mins: float = 0.0,
    ) -> None:
        """Update all state and performance metrics after a trade closes."""
        self.daily_pnl += pnl
        self.total_pnl += pnl
        self.current_balance += pnl
        self.trades_today += 1
        self.total_trades += 1
        self.monthly_trades += 1

        # Win/loss tracking
        if pnl >= 0:
            self.consecutive_losses = 0
            self.winning_trades += 1
            self.total_win_pnl += pnl
            self.total_win_duration_mins += duration_mins
        else:
            self.consecutive_losses += 1
            self.losses_today += 1
            self.losing_trades += 1
            self.total_loss_pnl += abs(pnl)
            self.total_loss_duration_mins += duration_mins
            if abs(pnl) > self.max_single_loss:
                self.max_single_loss = abs(pnl)

        # Directional tracking
        if direction.upper() == "BUY":
            self.long_profit += pnl
        else:
            self.short_profit += pnl

        # Weekday tracking
        weekday = datetime.utcnow().weekday()
        if weekday in self.weekday_stats:
            self.weekday_stats[weekday]["trades"] += 1
            self.weekday_stats[weekday]["pnl"] += pnl

        # Symbol tracking
        if symbol not in self.symbol_stats:
            self.symbol_stats[symbol] = {"trades": 0, "pnl": 0.0, "wins": 0}
        self.symbol_stats[symbol]["trades"] += 1
        self.symbol_stats[symbol]["pnl"] += pnl
        if pnl >= 0:
            self.symbol_stats[symbol]["wins"] += 1

        # Peak balance
        if self.current_balance > self.peak_balance:
            self.peak_balance = self.current_balance

        # Log the trade
        self.trade_log.append({
            "pnl": pnl,
            "direction": direction,
            "symbol": symbol,
            "duration_mins": duration_mins,
            "weekday": weekday,
            "balance_after": self.current_balance,
            "timestamp": datetime.utcnow().isoformat(),
        })

    def start_new_trading_day(self) -> None:
        """Reset daily counters at the start of each trading day.

        In compound mode, consecutive losses reset each day so the agent
        trades again (at auto-reduced size). In prop firm mode, the streak
        persists until a win resets it.
        """
        self.daily_starting_balance = self.current_balance
        self.daily_pnl = 0.0
        self.trades_today = 0
        self.losses_today = 0
        self.session_stopped = False
        self.total_trading_days += 1

        if self.is_compound_mode:
            self.consecutive_losses = 0

        # Monthly trade counter reset
        now = datetime.utcnow()
        month_key = (now.year, now.month)
        if self.current_month != month_key:
            self.monthly_trades = 0
            self.current_month = month_key

    # ── Performance Metrics ──────────────────────────────────────────

    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Calculate all core performance metrics for the challenge.

        Metrics:
        - ML vs AW: Max Loss / Avg Win (target < 1.0, elite < 0.5)
        - Profit Factor: Gross Wins / Gross Losses (target > 1.75)
        - Win/Loss Duration Ratio (target > 2.0)
        - Win % (target > 60%)
        - Trade frequency
        - Directional bias consistency
        """
        metrics = {}

        # Win percentage
        if self.total_trades > 0:
            metrics["win_pct"] = round(
                self.winning_trades / self.total_trades * 100, 1)
        else:
            metrics["win_pct"] = 0.0

        # Average win
        avg_win = (self.total_win_pnl / self.winning_trades
                   if self.winning_trades > 0 else 0.0)
        metrics["avg_win"] = round(avg_win, 2)

        # Average loss
        avg_loss = (self.total_loss_pnl / self.losing_trades
                    if self.losing_trades > 0 else 0.0)
        metrics["avg_loss"] = round(avg_loss, 2)

        # ML vs AW (Max Loss / Average Win) - target < 1.0
        if avg_win > 0:
            metrics["ml_vs_aw"] = round(self.max_single_loss / avg_win, 2)
        else:
            metrics["ml_vs_aw"] = None
        metrics["max_single_loss"] = round(self.max_single_loss, 2)

        # Profit Factor - target > 1.75
        if self.total_loss_pnl > 0:
            metrics["profit_factor"] = round(
                self.total_win_pnl / self.total_loss_pnl, 2)
        elif self.total_win_pnl > 0:
            metrics["profit_factor"] = float('inf')
        else:
            metrics["profit_factor"] = 0.0

        # Win/Loss Duration Ratio - target > 2.0
        if self.total_loss_duration_mins > 0:
            metrics["duration_ratio"] = round(
                self.total_win_duration_mins / self.total_loss_duration_mins, 2)
        else:
            metrics["duration_ratio"] = None

        # Trade frequency
        metrics["total_trades"] = self.total_trades
        metrics["monthly_trades"] = self.monthly_trades
        metrics["trades_today"] = self.trades_today
        metrics["losses_today"] = self.losses_today

        # Directional bias
        total_dir_profit = abs(self.long_profit) + abs(self.short_profit)
        if total_dir_profit > 0:
            dominant = max(self.long_profit, self.short_profit)
            metrics["dominant_direction"] = (
                "LONG" if self.long_profit >= self.short_profit else "SHORT")
            metrics["bias_pct"] = round(
                max(self.long_profit, self.short_profit)
                / total_dir_profit * 100, 1)
        else:
            metrics["dominant_direction"] = "NONE"
            metrics["bias_pct"] = 0.0

        # Best trading days
        best_days = sorted(
            self.weekday_stats.items(),
            key=lambda x: x[1]["pnl"],
            reverse=True,
        )
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri"]
        metrics["best_days"] = [
            {"day": day_names[d], "pnl": round(s["pnl"], 2), "trades": int(s["trades"])}
            for d, s in best_days if s["trades"] > 0
        ]

        # Top symbols
        top_symbols = sorted(
            self.symbol_stats.items(),
            key=lambda x: x[1]["pnl"],
            reverse=True,
        )
        metrics["top_symbols"] = [
            {"symbol": sym, "pnl": round(s["pnl"], 2),
             "trades": int(s["trades"]),
             "win_rate": round(s["wins"] / s["trades"] * 100, 1) if s["trades"] > 0 else 0}
            for sym, s in top_symbols[:3]
        ]

        # Health flags
        flags = []
        if metrics.get("ml_vs_aw") is not None and metrics["ml_vs_aw"] >= 1.0:
            flags.append("ML_vs_AW >= 1.0: max loss exceeds avg win")
        if metrics["profit_factor"] < 1.0 and self.total_trades >= 5:
            flags.append("Profit Factor < 1.0: losing overall")
        if metrics["win_pct"] < 50 and self.total_trades >= 5:
            flags.append("Win rate below 50%")
        if self.monthly_trades > 15:
            flags.append(f"Approaching monthly trade cap ({self.monthly_trades}/20)")
        if self.losses_today >= 3:
            flags.append("3+ losses today: STOP TRADING")
        metrics["health_flags"] = flags

        return metrics

    def should_reduce_exposure(self) -> tuple:
        """
        Check if performance metrics warrant reducing exposure.
        Returns (should_reduce: bool, reason: str).
        """
        if self.total_trades < 5:
            return False, ""

        metrics = self.get_performance_metrics()

        if metrics.get("ml_vs_aw") is not None and metrics["ml_vs_aw"] >= 1.0:
            return True, "ML/AW ratio >= 1.0 - reduce size"
        if metrics["profit_factor"] < 1.0:
            return True, "Profit factor < 1.0 - increase selectivity"
        if metrics["win_pct"] < 50:
            return True, "Win rate below 50% - tighten entries"
        if self.monthly_trades >= 15:
            return True, f"Monthly trades at {self.monthly_trades} - slow down"

        return False, ""

    def get_target_progress_pct(self) -> float:
        """How far toward the profit target (0-100+)."""
        if self.profit_target <= 0:
            return 0.0
        return (self.total_pnl / self.profit_target) * 100

    def is_challenge_passed(self) -> bool:
        """Check if the challenge profit target has been met."""
        return self.current_balance >= self.target_balance

    def get_challenge_status(self, current_balance: Optional[float] = None) -> Dict[str, Any]:
        """Get comprehensive challenge status for the agent prompt."""
        bal = current_balance or self.current_balance
        risk_pct = self.get_current_risk_percent()

        # Remaining to target
        remaining = max(0, self.target_balance - bal)
        avg_win = bal * risk_pct / 100 * self.min_rr_ratio
        est_trades = int(remaining / avg_win) + 1 if avg_win > 0 else 999

        # Drawdown room remaining
        if self.drawdown_type in ("trailing", "trailing_relative"):
            dd_used = self.peak_balance - bal
        else:
            dd_used = self.account_size - bal
        dd_remaining = max(0, self.firm_max_drawdown - dd_used)

        # Daily loss room remaining
        daily_room = max(0, self.personal_daily_loss_cap + self.daily_pnl)

        should_stop, stop_reason = self.should_stop_trading_session()

        return {
            "mode": "challenge" if self.challenge_mode else "standard",
            "challenge_type": self.challenge_type,
            "phase": self.current_phase,
            "account_size": self.account_size,
            "balance": round(bal, 2),
            "target_balance": round(self.target_balance, 2),
            "profit_target": round(self.profit_target, 2),
            "profit_target_pct": self.profit_target_pct,
            "total_pnl": round(self.total_pnl, 2),
            "progress_pct": round(self.get_target_progress_pct(), 1),
            "remaining_to_target": round(remaining, 2),
            "est_trades_to_target": est_trades,
            "peak_balance": round(self.peak_balance, 2),
            "drawdown_used": round(dd_used, 2),
            "drawdown_room_remaining": round(dd_remaining, 2),
            "drawdown_type": self.drawdown_type,
            "firm_daily_limit": round(self.firm_daily_loss_limit, 2),
            "firm_max_drawdown": round(self.firm_max_drawdown, 2),
            "daily_pnl": round(self.daily_pnl, 2),
            "daily_loss_room": round(daily_room, 2),
            "personal_daily_cap": round(self.personal_daily_loss_cap, 2),
            "trades_today": self.trades_today,
            "max_trades_today": self.max_trades_per_day,
            "consecutive_losses": self.consecutive_losses,
            "trading_days": self.total_trading_days,
            "min_trading_days": self.min_trading_days,
            "current_risk_pct": risk_pct,
            "risk_per_trade_usd": round(bal * risk_pct / 100, 2),
            "min_rr_ratio": self.min_rr_ratio,
            "max_sl_pips": self.max_sl_pips,
            "min_sl_pips": self.min_sl_pips,
            "max_spread_pips": self.max_spread_pips,
            "should_stop": should_stop,
            "stop_reason": stop_reason,
            "is_passed": self.is_challenge_passed(),
            "weekend_holding_allowed": self.weekend_holding_allowed,
            "losses_today": self.losses_today,
            "monthly_trades": self.monthly_trades,
            "is_compound_mode": self.is_compound_mode,
            "account_currency": self.challenge_config.get("account_currency", "USD"),
            "stop_after_consecutive_losses": self.stop_after_consecutive_losses,
            "milestones": self.milestones,
            "current_milestone": self._get_current_milestone(bal),
            "max_risk_pct": self.max_risk_percent,
            "performance": self.get_performance_metrics(),
        }

    # ── Trading Session Control ──────────────────────────────────────

    def is_valid_trading_time(self) -> bool:
        """Check if current UTC time is within allowed trading sessions."""
        now = datetime.utcnow()

        weekday = now.weekday()
        hour = now.hour
        if weekday == 5:  # Saturday
            return False
        if weekday == 6:  # Sunday
            return hour >= 22
        if weekday == 4 and hour >= 22:  # Friday close
            return False

        if "all" in self.trading_sessions:
            return True

        session_windows = {
            "london_ny_overlap": (13, 17),
            "london": (8, 16),
            "new_york": (13, 22),
            "asian": (0, 8),
        }

        for session in self.trading_sessions:
            if session in session_windows:
                start_hour, end_hour = session_windows[session]
                if start_hour <= hour < end_hour:
                    return True

        return False

    # ── Core Trading Loop ────────────────────────────────────────────

    async def run_trading_session(self, session_id: str) -> None:
        """Run a single trading analysis cycle."""
        print(f"Starting forex trading cycle: {session_id}")

        # Safety check before starting
        should_stop, reason = self.should_stop_trading_session()
        if should_stop:
            print(f"SKIPPING session - {reason}")
            return

        log_file = self._setup_logging(session_id)
        write_config_value("LOG_FILE", log_file)

        self.agent = create_agent(
            self.model,
            tools=self.tools,
            system_prompt=get_agent_system_prompt_forex(
                session_id=session_id,
                signature=self.signature,
                forex_symbols=self.forex_symbols,
                challenge_status=self.get_challenge_status(),
            ),
        )

        user_query = [{"role": "user", "content": (
            f"Analyze current forex market conditions for session {session_id}. "
            f"Check prices, spreads, and news. Only trade if there is a "
            f"high-probability setup that meets ALL your trading plan criteria. "
            f"If nothing qualifies, output {STOP_SIGNAL} and wait."
        )}]
        message = user_query.copy()
        self._log_message(log_file, user_query)

        current_step = 0
        while current_step < self.max_steps:
            current_step += 1
            print(f"Step {current_step}/{self.max_steps}")

            try:
                response = await self._ainvoke_with_retry(message)
                agent_response = extract_conversation(response, "final")

                if STOP_SIGNAL in agent_response:
                    print("Agent decided: no trade this cycle")
                    self._log_message(
                        log_file,
                        [{"role": "assistant", "content": agent_response}])
                    break

                tool_msgs = extract_tool_messages(response)
                tool_response = "\n".join([msg.content for msg in tool_msgs])

                new_messages = [
                    {"role": "assistant", "content": agent_response},
                    {"role": "user", "content": f"Tool results: {tool_response}"},
                ]
                message.extend(new_messages)
                self._log_message(log_file, new_messages[0])
                self._log_message(log_file, new_messages[1])

            except Exception as e:
                print(f"Trading cycle error: {e}")
                raise

        await self._handle_trading_result(session_id)

    def _setup_logging(self, session_id: str) -> str:
        log_path = os.path.join(
            self.base_log_path, self.signature, "log", session_id)
        if not os.path.exists(log_path):
            os.makedirs(log_path)
        return os.path.join(log_path, "log.jsonl")

    def _log_message(self, log_file: str, new_messages) -> None:
        log_entry = {
            "signature": self.signature,
            "timestamp": datetime.utcnow().isoformat(),
            "new_messages": new_messages,
        }
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    async def _ainvoke_with_retry(self, message: List[Dict[str, str]]) -> Any:
        for attempt in range(1, self.max_retries + 1):
            try:
                return await self.agent.ainvoke(
                    {"messages": message}, {"recursion_limit": 100}
                )
            except Exception as e:
                if attempt == self.max_retries:
                    raise e
                wait = self.base_delay * (2 ** (attempt - 1))
                print(f"Attempt {attempt} failed, retrying in {wait}s: {e}")
                await asyncio.sleep(wait)

    async def _handle_trading_result(self, session_id: str) -> None:
        if_trade = get_config_value("IF_TRADE")
        if if_trade:
            write_config_value("IF_TRADE", False)
            print(f"Trade executed in session {session_id}")
        else:
            print(f"No trade in session {session_id}")
            write_config_value("IF_TRADE", False)

    async def run_live_loop(self) -> None:
        """Continuous live trading loop with full status display."""
        print(f"Starting live forex trading loop")
        print(f"Interval: {self.loop_interval_seconds}s")
        print(f"Sessions: {self.trading_sessions}")
        print(f"Pairs: {self.forex_symbols}")
        ccy = self.challenge_config.get("account_currency", "$")
        if self.challenge_mode:
            print(f"Challenge: {self.challenge_type} | "
                  f"Target: {ccy}{self.target_balance:,.0f}")

        cycle = 0
        current_trading_date = None
        while True:
            try:
                # Reset daily state when the date changes
                today = datetime.utcnow().strftime("%Y-%m-%d")
                if today != current_trading_date:
                    current_trading_date = today
                    self.start_new_trading_day()
                    print(f"\n--- New trading day: {today} ---")

                if not self.is_valid_trading_time():
                    print(f"Outside trading session. "
                          f"Sleeping {self.loop_interval_seconds}s...")
                    await asyncio.sleep(self.loop_interval_seconds)
                    continue

                cycle += 1
                session_id = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
                status = self.get_challenge_status()
                ccy = status.get("account_currency", "$")
                print(f"\n{'='*60}")
                print(f"Cycle {cycle} | {session_id}")
                print(f"Balance: {ccy}{status['balance']:,.2f} | "
                      f"P/L: {ccy}{status['total_pnl']:+,.2f} | "
                      f"Progress: {status['progress_pct']:.1f}% | "
                      f"Risk: {status['current_risk_pct']}%")
                print(f"DD room: {ccy}{status['drawdown_room_remaining']:,.0f} | "
                      f"Daily room: {ccy}{status['daily_loss_room']:,.0f} | "
                      f"Trades today: {status['trades_today']}/{status['max_trades_today']}")
                print(f"{'='*60}")

                if self.is_challenge_passed():
                    print("CHALLENGE PASSED! Profit target reached.")
                    break

                should_stop, reason = self.should_stop_trading_session()
                if should_stop:
                    print(f"Session stopped: {reason}")
                    await asyncio.sleep(self.loop_interval_seconds)
                    continue

                await self.run_trading_session(session_id)

                print(f"Sleeping {self.loop_interval_seconds}s...")
                await asyncio.sleep(self.loop_interval_seconds)

            except KeyboardInterrupt:
                print("\nLive loop stopped by user")
                break
            except Exception as e:
                print(f"Cycle error: {e}")
                await asyncio.sleep(self.loop_interval_seconds * 2)

    # ── Compatibility Methods ────────────────────────────────────────

    def register_agent(self) -> None:
        if os.path.exists(self.position_file):
            print(f"Position file already exists, skipping registration")
            return

        position_dir = os.path.join(self.data_path, "position")
        if not os.path.exists(position_dir):
            os.makedirs(position_dir)

        init_position = {symbol: 0.0 for symbol in self.forex_symbols}
        init_position["CASH"] = self.initial_cash

        with open(self.position_file, "w") as f:
            f.write(json.dumps({
                "date": self.init_date,
                "id": 0,
                "positions": init_position,
                "challenge_state": self.get_challenge_status(),
            }) + "\n")

        ccy = self.challenge_config.get("account_currency", "$")
        print(f"Forex Agent {self.signature} registered")
        print(f"Balance: {ccy}{self.initial_cash:,.0f}")
        print(f"Pairs: {len(self.forex_symbols)}")

    def get_trading_dates(self, init_date: str, end_date: str) -> List[str]:
        dates = []
        start = datetime.strptime(init_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")

        current = start + timedelta(days=1)
        while current <= end:
            if current.weekday() < 5:
                dates.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)

        return dates

    async def run_date_range(self, init_date: str, end_date: str) -> None:
        print(f"Running forex date range: {init_date} to {end_date}")
        trading_dates = self.get_trading_dates(init_date, end_date)

        if not trading_dates:
            print("No trading days to process")
            return

        print(f"Trading days: {len(trading_dates)}")

        for date in trading_dates:
            self.start_new_trading_day()
            write_config_value("TODAY_DATE", date)
            write_config_value("SIGNATURE", self.signature)

            if self.is_challenge_passed():
                print(f"CHALLENGE PASSED on {date}! "
                      f"Balance: ${self.current_balance:,.2f}")
                break

            try:
                await self.run_with_retry(date)
            except Exception as e:
                print(f"Error on {date}: {e}")
                raise

        print(f"Forex processing completed for {self.signature}")

    async def run_with_retry(self, session_id: str) -> None:
        for attempt in range(1, self.max_retries + 1):
            try:
                await self.run_trading_session(session_id)
                return
            except Exception as e:
                if attempt == self.max_retries:
                    raise
                wait = self.base_delay * attempt
                print(f"Attempt {attempt} failed, retrying in {wait}s: {e}")
                await asyncio.sleep(wait)

    def get_position_summary(self) -> Dict[str, Any]:
        if not os.path.exists(self.position_file):
            return {"error": "Position file does not exist"}

        positions = []
        with open(self.position_file, "r") as f:
            for line in f:
                positions.append(json.loads(line))

        if not positions:
            return {"error": "No position records"}

        latest = positions[-1]
        return {
            "signature": self.signature,
            "latest_date": latest.get("date"),
            "positions": latest.get("positions", {}),
            "total_records": len(positions),
            "challenge_state": latest.get("challenge_state", {}),
        }

    def __str__(self) -> str:
        mode = (f"CHALLENGE-{self.challenge_type.upper()}"
                if self.challenge_mode else "STANDARD")
        return (
            f"BaseAgentForex(signature='{self.signature}', "
            f"basemodel='{self.basemodel}', "
            f"pairs={len(self.forex_symbols)}, "
            f"mode={mode}, "
            f"balance=${self.account_size:,.0f}, "
            f"risk={self.risk_percent}%/trade)"
        )

    def __repr__(self) -> str:
        return self.__str__()
