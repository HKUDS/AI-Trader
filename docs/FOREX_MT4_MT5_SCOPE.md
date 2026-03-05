# AI-Trader: Autonomous Forex Agent for MT4/MT5

## Monetization & Live Trading Scope Document

> **Goal**: Build an autonomous AI forex trading agent that connects to MetaTrader 4/5,
> manages risk, and executes a compounding challenge strategy targeting 20 pips per trade
> to grow accounts from $20 to $50k repeatedly.

---

## 1. THE COMPOUNDING CHALLENGE STRATEGY

### The Math

Starting with $20, risking 30% of balance per trade, targeting 20 pips per trade:

| Level | Balance Before | Risk (30%) | Lot Size | 20-Pip Profit | Balance After |
|-------|---------------|------------|----------|---------------|---------------|
| 1     | $20.00        | $6.00      | 0.003    | $6.00         | $26.00        |
| 2     | $26.00        | $7.80      | 0.004    | $7.80         | $33.80        |
| 3     | $33.80        | $10.14     | 0.005    | $10.14        | $43.94        |
| 4     | $43.94        | $13.18     | 0.007    | $13.18        | $57.12        |
| 5     | $57.12        | $17.14     | 0.009    | $17.14        | $74.26        |
| ...   | ...           | ...        | ...      | ...           | ...           |
| 10    | $275.72       | $82.72     | 0.041    | $82.72        | $358.43       |
| 15    | $1,026.28     | $307.88    | 0.154    | $307.88       | $1,334.17     |
| 20    | $3,819.84     | $1,145.95  | 0.573    | $1,145.95     | $4,965.80     |
| 25    | $14,213.95    | $4,264.19  | 2.132    | $4,264.19     | $18,478.14    |
| 30    | $52,896.78    | $15,869.03 | 7.935    | $15,869.03    | **$68,765.82**|

**The cycle**: Hit ~$50k target -> withdraw profits -> reset to $20 -> repeat.

### What This Requires From the Agent

- **30 consecutive winning trades** of exactly 20 pips each (with no losses)
- **Win rate required**: 100% for full compound (unrealistic in real markets)
- **Realistic adjusted model** (see Section 7 for modified approach)

### Pip Value Reference (EUR/USD)

| Lot Size | Units   | Pip Value | 20 Pips = |
|----------|---------|-----------|-----------|
| 0.001    | 100     | $0.01     | $0.20     |
| 0.01     | 1,000   | $0.10     | $2.00     |
| 0.1      | 10,000  | $1.00     | $20.00    |
| 1.0      | 100,000 | $10.00    | $200.00   |

---

## 2. MT4/MT5 INTEGRATION OPTIONS

### Option A: MT5 Native Python Package (RECOMMENDED for Windows VPS)

```
pip install MetaTrader5
```

| Aspect          | Details                                          |
|-----------------|--------------------------------------------------|
| **Latency**     | 1-5ms (IPC, same machine)                        |
| **Platform**    | Windows only (runs alongside MT5 terminal)       |
| **Cost**        | Free                                             |
| **Live Trading**| Yes, full support                                |
| **Reliability** | Excellent (official MetaQuotes integration)      |
| **Setup**       | Install MT5 terminal + Python package            |

```python
import MetaTrader5 as mt5

mt5.initialize()
mt5.login(account=12345, password="pass", server="Broker-Live")

# Get price
tick = mt5.symbol_info_tick("EURUSD")
print(f"Bid: {tick.bid}, Ask: {tick.ask}")

# Place order
request = {
    "action": mt5.TRADE_ACTION_DEAL,
    "symbol": "EURUSD",
    "volume": 0.01,
    "type": mt5.ORDER_TYPE_BUY,
    "price": tick.ask,
    "sl": tick.ask - 0.0020,  # 20 pip stop loss
    "tp": tick.ask + 0.0020,  # 20 pip take profit
    "magic": 234000,
    "comment": "AI-Trader Forex Agent",
}
result = mt5.order_send(request)
```

### Option B: MetaApi Cloud (RECOMMENDED for Linux/Mac/Remote)

```
pip install metaapi-cloud-sdk
```

| Aspect          | Details                                          |
|-----------------|--------------------------------------------------|
| **Latency**     | 50-200ms (cloud relay)                           |
| **Platform**    | Any (Linux, Mac, Windows, Docker)                |
| **Cost**        | Free tier (1 account), $20/mo+ for more          |
| **Live Trading**| Yes, MT4 and MT5                                 |
| **Reliability** | Good (cloud-managed)                             |
| **Setup**       | Create metaapi.cloud account, connect broker     |

```python
from metaapi_cloud_sdk import MetaApi

api = MetaApi('your-token')
account = await api.metatrader_account_api.get_account('account-id')
connection = account.get_rpc_connection()
await connection.connect()

# Get price
price = await connection.get_symbol_price('EURUSD')

# Place order
result = await connection.create_market_buy_order(
    'EURUSD', 0.01,
    stop_loss=price['ask'] - 0.0020,
    take_profit=price['ask'] + 0.0020,
    comment='AI-Trader Forex Agent'
)
```

### Option C: ZeroMQ Bridge (DWX Connector)

| Aspect          | Details                                          |
|-----------------|--------------------------------------------------|
| **Latency**     | 5-20ms (local IPC)                               |
| **Platform**    | MT4/MT5 on Windows, Python anywhere on network   |
| **Cost**        | Free (open source)                               |
| **Live Trading**| Yes                                              |
| **Reliability** | Good, but requires MQL EA running in terminal    |

### Recommendation

| Scenario                      | Best Option       |
|-------------------------------|-------------------|
| Windows VPS, single broker    | **MT5 Native**    |
| Linux server, multiple brokers| **MetaApi Cloud** |
| Low latency + flexibility     | **ZeroMQ Bridge** |
| Starting out / prototyping    | **MetaApi Cloud** |

---

## 3. ARCHITECTURE: Extending AI-Trader for Forex

### New Files to Create

```
AI-Trader/
├── agent/
│   └── base_agent_forex/
│       ├── __init__.py
│       └── base_agent_forex.py          # Core forex trading agent
├── agent_tools/
│   ├── tool_forex_trade.py              # MCP tool: buy/sell forex via MT4/MT5
│   └── mt4_mt5_adapter.py              # Broker connection abstraction layer
├── prompts/
│   └── agent_prompt_forex.py            # Forex-specific AI system prompt
├── configs/
│   ├── forex_config.json                # Forex agent configuration
│   └── forex_challenge_config.json      # Compounding challenge mode config
├── data/
│   └── forex/
│       └── agent_data_forex/            # Forex trading logs
├── tools/
│   └── forex_risk_manager.py           # Challenge-mode risk management
└── scripts/
    ├── main_forex_step1-3.sh            # Forex launch scripts
    └── challenge_monitor.py             # Compound challenge progress tracker
```

### Files to Modify

| File | Changes |
|------|---------|
| `main.py` | Add `BaseAgentForex` to `AGENT_REGISTRY`, forex market detection |
| `tools/price_tools.py` | Add forex symbol lists, pip calculations |
| `agent_tools/start_mcp_services.py` | Add forex trade service startup |
| `.env.example` | Add `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`, `METAAPI_TOKEN` |

---

## 4. CORE COMPONENT DESIGNS

### 4.1 MT4/MT5 Adapter Layer

```python
# agent_tools/mt4_mt5_adapter.py

class MT4MT5Adapter:
    """
    Unified interface for MT4/MT5 broker communication.
    Supports: Native MT5, MetaApi, ZeroMQ backends.
    """

    def __init__(self, backend: str = "mt5_native", config: dict = {}):
        self.backend = backend
        self.config = config

    async def connect(self) -> bool:
        """Establish connection to broker"""

    async def get_price(self, symbol: str) -> dict:
        """Returns {'bid': float, 'ask': float, 'spread': float, 'time': str}"""

    async def market_buy(self, symbol: str, lots: float,
                         sl_pips: float = None, tp_pips: float = None) -> dict:
        """Execute market buy order with optional SL/TP in pips"""

    async def market_sell(self, symbol: str, lots: float,
                          sl_pips: float = None, tp_pips: float = None) -> dict:
        """Execute market sell order with optional SL/TP in pips"""

    async def close_position(self, ticket: int) -> dict:
        """Close specific position by ticket number"""

    async def get_account_info(self) -> dict:
        """Returns {balance, equity, margin, free_margin, leverage, profit}"""

    async def get_open_positions(self) -> list:
        """Returns list of all open positions with P/L"""

    async def get_trade_history(self, days: int = 7) -> list:
        """Returns recent closed trades"""
```

### 4.2 Forex Trade MCP Tool

```python
# agent_tools/tool_forex_trade.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ForexTradeTools")

@mcp.tool()
async def buy_forex(symbol: str, lots: float,
                    stop_loss_pips: float = 20,
                    take_profit_pips: float = 20) -> dict:
    """
    Buy a forex pair via MT4/MT5.

    Args:
        symbol: Forex pair (e.g., "EURUSD")
        lots: Position size (0.01 = micro lot)
        stop_loss_pips: Stop loss distance in pips (default: 20)
        take_profit_pips: Take profit distance in pips (default: 20)

    Returns:
        Order result with ticket number, fill price, etc.
    """

@mcp.tool()
async def sell_forex(symbol: str, lots: float,
                     stop_loss_pips: float = 20,
                     take_profit_pips: float = 20) -> dict:
    """Sell a forex pair via MT4/MT5."""

@mcp.tool()
async def close_forex_position(ticket: int) -> dict:
    """Close a specific open position."""

@mcp.tool()
async def get_account_summary() -> dict:
    """Get current account balance, equity, margin, open P/L."""

@mcp.tool()
async def get_open_trades() -> list:
    """List all currently open forex positions."""

@mcp.tool()
async def calculate_lot_size(
    balance: float, risk_percent: float,
    stop_loss_pips: float, symbol: str = "EURUSD"
) -> dict:
    """
    Calculate correct lot size for risk management.

    Given balance=$100, risk=30%, SL=20 pips on EURUSD:
    Risk amount = $30
    Pip value needed = $30 / 20 pips = $1.50/pip
    Lot size = $1.50 / $10 (pip value per standard lot) = 0.15 lots
    """
```

### 4.3 Forex Agent Prompt

```python
# prompts/agent_prompt_forex.py

FOREX_SYSTEM_PROMPT = """
You are an autonomous forex trading agent connected to a live MT4/MT5 account.

## YOUR MISSION
Manage risk and maximize profitability through disciplined forex trading.

## CURRENT ACCOUNT STATE
- Date/Time: {datetime}
- Balance: ${balance}
- Equity: ${equity}
- Free Margin: ${free_margin}
- Margin Level: {margin_level}%
- Leverage: {leverage}:1
- Open P/L: ${open_pl}

## OPEN POSITIONS
{open_positions}

## CHALLENGE MODE STATUS
- Current Level: {challenge_level}/30
- Target per trade: 20 pips
- Risk per trade: {risk_percent}% of balance
- Next lot size: {next_lot_size}
- Wins in a row: {consecutive_wins}
- Session target: ${session_target}

## AVAILABLE PAIRS
{available_pairs}

## CURRENT PRICES (Bid/Ask/Spread)
{current_prices}

## RECENT TRADE HISTORY
{trade_history}

## TRADING RULES
1. ONE trade at a time - never have multiple positions open
2. Every trade MUST have a stop loss (max 20 pips)
3. Every trade MUST have a take profit (20 pips)
4. Calculate lot size using the risk management tool BEFORE every trade
5. Only trade during high-liquidity sessions (London/NY overlap: 13:00-17:00 UTC)
6. Do NOT trade during major news events (NFP, FOMC, ECB)
7. Wait for clear setups - no trade is better than a bad trade
8. If 2 consecutive losses occur, STOP trading for the session

## DECISION FRAMEWORK
For each potential trade, evaluate:
1. Is the spread acceptable? (< 2 pips for majors)
2. Is there a clear directional bias? (trend, support/resistance, momentum)
3. Is the risk:reward ratio at least 1:1?
4. Is this a high-probability setup?
5. Are there upcoming news events that could cause volatility?

Use the tools available to get prices, calculate lot sizes, and execute trades.
When you have no good setup, output {STOP_SIGNAL} and wait.

{STOP_SIGNAL}
"""
```

### 4.4 Risk Manager (Challenge Mode)

```python
# tools/forex_risk_manager.py

class ChallengeRiskManager:
    """
    Manages the compounding challenge:
    $20 -> $50k in 30 winning trades, then reset.
    """

    def __init__(self, starting_balance: float = 20.0,
                 risk_percent: float = 30.0,
                 target_pips: float = 20.0,
                 target_balance: float = 50000.0):
        self.starting_balance = starting_balance
        self.risk_percent = risk_percent
        self.target_pips = target_pips
        self.target_balance = target_balance
        self.level = 0
        self.consecutive_wins = 0

    def calculate_lot_size(self, current_balance: float,
                           symbol: str = "EURUSD") -> float:
        """
        Calculate lot size for current challenge level.

        Risk amount = balance * risk_percent
        Pip value needed = risk_amount / target_pips
        Lot size = pip_value_needed / pip_value_per_lot
        """
        risk_amount = current_balance * (self.risk_percent / 100)
        pip_value_needed = risk_amount / self.target_pips

        # Pip value per standard lot varies by pair
        pip_values = {
            "EURUSD": 10.0, "GBPUSD": 10.0, "AUDUSD": 10.0,
            "NZDUSD": 10.0, "USDCHF": 10.0, "USDCAD": 10.0,
            "USDJPY": 6.67,  # Approximate, varies with USD/JPY rate
        }

        pip_value_per_lot = pip_values.get(symbol, 10.0)
        lot_size = pip_value_needed / pip_value_per_lot

        # Round down to nearest 0.001 (micro lot increment)
        lot_size = max(0.001, round(lot_size, 3))
        return lot_size

    def on_trade_result(self, pips: float, profit: float):
        """Track challenge progress after each trade."""
        if pips >= self.target_pips:
            self.consecutive_wins += 1
            self.level += 1
        else:
            # Loss resets the consecutive counter
            # (but NOT the balance - we keep what we have)
            self.consecutive_wins = 0

    def should_reset(self, current_balance: float) -> bool:
        """Check if target reached, time to withdraw and restart."""
        return current_balance >= self.target_balance

    def get_status(self, current_balance: float) -> dict:
        return {
            "level": self.level,
            "consecutive_wins": self.consecutive_wins,
            "balance": current_balance,
            "target": self.target_balance,
            "progress_pct": (current_balance / self.target_balance) * 100,
            "next_lot": self.calculate_lot_size(current_balance),
        }
```

### 4.5 Forex Configuration

```json
// configs/forex_challenge_config.json
{
    "agent_type": "BaseAgentForex",
    "market": "forex",
    "mode": "live_challenge",

    "mt4_mt5_config": {
        "backend": "mt5_native",
        "login": "${MT5_LOGIN}",
        "password": "${MT5_PASSWORD}",
        "server": "${MT5_SERVER}",
        "timeout": 10000
    },

    "challenge_config": {
        "starting_balance": 20.0,
        "target_balance": 50000.0,
        "risk_percent_per_trade": 30.0,
        "target_pips": 20,
        "max_spread_pips": 2.0,
        "max_concurrent_trades": 1,
        "stop_after_consecutive_losses": 2,
        "trading_sessions": ["london_ny_overlap"],
        "avoid_news_events": true
    },

    "trading_pairs": [
        "EURUSD", "GBPUSD", "USDJPY", "USDCHF",
        "AUDUSD", "NZDUSD", "USDCAD"
    ],

    "models": [
        {
            "name": "claude-opus-4-6",
            "basemodel": "anthropic/claude-opus-4-6",
            "signature": "claude-opus-forex",
            "enabled": true
        }
    ],

    "agent_config": {
        "max_steps": 50,
        "max_retries": 3,
        "base_delay": 2.0,
        "initial_cash": 20.0
    },

    "risk_management": {
        "max_daily_loss_percent": 5.0,
        "max_total_drawdown_percent": 10.0,
        "require_sl_on_every_trade": true,
        "require_tp_on_every_trade": true,
        "max_sl_pips": 25,
        "min_rr_ratio": 1.0
    },

    "log_config": {
        "log_path": "./data/agent_data_forex"
    }
}
```

---

## 5. AGENT DECISION LOOP (How It Trades)

### Continuous Live Trading Flow

```
┌─────────────────────────────────────────────────┐
│            FOREX AGENT MAIN LOOP                 │
│                                                  │
│  1. Wake up (every N minutes during sessions)    │
│  2. Check: Is it a valid trading window?         │
│     - London/NY overlap (13:00-17:00 UTC)        │
│     - No pending news events in next 30 min      │
│     - Not weekend (Fri 22:00 - Sun 22:00 UTC)    │
│  3. Check: Any open positions?                   │
│     - If yes: monitor, trail stop if profitable  │
│     - If no: scan for setups                     │
│  4. AI Analysis:                                 │
│     - Feed prices, spreads, account state to LLM │
│     - LLM reasons about direction, entry, timing │
│     - LLM calls calculate_lot_size tool          │
│     - LLM calls buy_forex or sell_forex          │
│  5. Risk check: Does trade pass all rules?       │
│     - SL/TP set? Lot size correct? Spread ok?    │
│  6. Execute or reject                            │
│  7. Log everything to position.jsonl             │
│  8. Update challenge progress                    │
│  9. Sleep until next cycle                       │
└─────────────────────────────────────────────────┘
```

### Key Difference from Existing AI-Trader

| Existing System | Forex Agent |
|----------------|-------------|
| Historical replay (backtesting) | **Live market execution** |
| Simulated fills at open price | **Real fills with slippage** |
| Daily or hourly cycles | **Continuous (every 1-5 min)** |
| No stop loss / take profit | **Mandatory SL/TP on every trade** |
| Multiple positions | **One position at a time** |
| Local JSONL = source of truth | **MT4/MT5 = source of truth** |
| No leverage | **Leveraged (50:1 to 500:1)** |

---

## 6. INFRASTRUCTURE REQUIREMENTS

### Recommended Setup

```
┌──────────────────────────────────────────┐
│              Windows VPS                  │
│         (e.g., Contabo, Vultr)            │
│                                          │
│  ┌────────────┐  ┌──────────────────┐   │
│  │  MT5        │  │  Python 3.11+    │   │
│  │  Terminal   │◄─┤                  │   │
│  │  (Broker)   │  │  AI-Trader       │   │
│  │             │  │  Forex Agent     │   │
│  └────────────┘  │                  │   │
│                   │  MCP Services    │   │
│                   │  (forex tools)   │   │
│                   │                  │   │
│                   │  LLM API calls   │──►│── Claude/GPT API
│                   └──────────────────┘   │
│                                          │
│  Cost: ~$10-30/month                     │
└──────────────────────────────────────────┘
```

### Alternative: Linux + MetaApi

```
┌──────────────────────────────────────────┐
│              Linux VPS                    │
│         (cheaper, more stable)            │
│                                          │
│  ┌──────────────────┐  ┌─────────────┐  │
│  │  Python 3.11+    │  │  MetaApi     │  │
│  │                  │  │  Cloud       │  │
│  │  AI-Trader       │─►│  (Relay to   │──┤──► MT4/MT5 at Broker
│  │  Forex Agent     │  │   broker)    │  │
│  │                  │  └─────────────┘  │
│  │  MCP Services    │                   │
│  └──────────────────┘                   │
│                                          │
│  Cost: ~$5-15/month + MetaApi $20/mo     │
└──────────────────────────────────────────┘
```

### Broker Requirements

| Requirement | Why |
|-------------|-----|
| MT4 or MT5 support | Required for automation |
| Micro lots (0.01) allowed | Needed for $20 starting balance |
| Nano lots (0.001) if possible | Better precision at low balances |
| Low spreads (< 1.5 pips EUR/USD) | 20-pip target needs tight spreads |
| High leverage (100:1 to 500:1) | Needed for 30% risk on small account |
| Fast execution (< 50ms) | Minimize slippage on 20-pip targets |
| No restrictions on EAs / bots | Some brokers ban automated trading |
| Low minimum deposit ($10-20) | Match challenge starting balance |

**Broker Suggestions**: IC Markets, Pepperstone, FP Markets, Exness, XM (all support MT4/MT5 with micro lots and allow EAs).

---

## 7. REALITY CHECK: Modified Strategy

### The Raw Math Problem

30 consecutive wins at 100% is unrealistic. Here's the probability:

| Win Rate | P(30 wins in a row) | Expected Attempts |
|----------|---------------------|-------------------|
| 50%      | 0.000000093%        | 1,073,741,824     |
| 60%      | 0.001%              | 87,791             |
| 70%      | 0.02%               | 4,394              |
| 80%      | 0.12%               | 808                |
| 90%      | 4.2%                | 24                 |
| 95%      | 21.5%               | 5                  |

### Realistic Modified Approach

Instead of requiring 30 CONSECUTIVE wins, use a **compounding with drawdown tolerance** model:

```
MODIFIED CHALLENGE RULES:
1. Start with $20
2. Risk 15-30% per trade (adaptive based on recent performance)
3. Target 20 pips per trade (1:1 risk/reward minimum)
4. Allow losses - they reduce balance but don't reset the challenge
5. Track net growth, not win streaks
6. Target: grow to $50k over time through compounding

With 65% win rate and 1:1 R:R:
- Expected per trade: (0.65 * 20) - (0.35 * 20) = +6 pips net
- Need ~250-400 trades to reach $50k from $20 (with compounding)
- At 1-3 trades per day = ~3-12 months per cycle
```

### Three Operating Modes

**Mode 1: Pure Challenge** (Original - Aggressive)
- 30% risk, 20 pip target
- Stop on first loss, restart from $20
- High risk, potential fast growth
- Probability: Very low per attempt, but infinite attempts

**Mode 2: Compound Growth** (Recommended - Balanced)
- 10-20% risk (adaptive)
- 20 pip target with trailing stops
- Allow losses, compound on net growth
- Target: $20 -> $50k over 3-6 months
- Much higher probability of success

**Mode 3: Steady Income** (Conservative)
- 2-5% risk per trade
- Target: consistent $500-2000/month on larger accounts
- Start with $1000-5000
- Sustainable long-term income

### Recommended Progression

```
Phase 1 (Weeks 1-4):   Demo account, tune AI decisions, measure win rate
Phase 2 (Weeks 5-8):   $20 live account, Mode 1 (pure challenge), multiple attempts
Phase 3 (Months 3-6):  Fund $500-2000, Mode 2 (compound growth)
Phase 4 (Month 6+):    Scale to Mode 3 (steady income) on proven strategy
```

---

## 8. WHAT MAKES THE AI AGENT VALUABLE

### Why AI > Traditional EA (Expert Advisor)

| Traditional EA | AI-Trader Forex Agent |
|---------------|----------------------|
| Fixed rules (if RSI > 70, sell) | **Reasons about context** |
| Can't read news | **Processes news via search tools** |
| Same logic forever | **Adapts reasoning per trade** |
| Brittle in changing markets | **Understands market regimes** |
| No explanation for trades | **Logs full reasoning chain** |
| Requires manual optimization | **Self-adjusting via LLM reasoning** |

### The AI Agent's Edge

1. **Multi-Factor Analysis**: Combines price action, spread conditions, session timing, news sentiment, and account state into every decision
2. **Risk Awareness**: Understands the challenge structure and adjusts behavior (e.g., more conservative at higher levels)
3. **Discipline**: No emotions, no revenge trading, no FOMO
4. **Adaptability**: Different LLMs bring different "personalities" - can A/B test models
5. **Full Audit Trail**: Every decision is logged with reasoning, enabling continuous improvement

---

## 9. MONETIZATION PATHS

### Path A: Personal Trading
- Run the agent on your own funded account
- Keep 100% of profits
- Risk: your own capital
- Setup cost: ~$50-100/month (VPS + API keys)

### Path B: Prop Firm Challenges (FTMO, The5ers, etc.)
- Pay $100-500 for a challenge account ($10k-200k)
- Pass challenge rules (profit target + drawdown limits)
- If funded: trade firm's capital, keep 70-90% of profits
- Risk: only the challenge fee
- **This is where the compounding strategy shines** - start small, prove the agent

### Path C: Signal Service
- Run the agent, broadcast trades as signals
- Subscribers copy-trade via MT4/MT5 copier
- Revenue: $50-200/month per subscriber
- Scales independently of account size

### Path D: SaaS Platform
- Package the forex agent as a product
- Users connect their own MT4/MT5 accounts
- Revenue: subscription model
- Requires: dashboard, user management, billing

### Path E: Managed Accounts (PAMM/MAM)
- Trade on behalf of investors via PAMM
- Take 20-30% performance fee
- Requires: regulatory considerations, track record

---

## 10. IMPLEMENTATION ROADMAP

### Phase 1: Foundation (Week 1-2)
- [ ] Create `agent/base_agent_forex/` with BaseAgentForex class
- [ ] Create `agent_tools/mt4_mt5_adapter.py` (MetaApi backend first)
- [ ] Create `agent_tools/tool_forex_trade.py` (MCP trade tools)
- [ ] Create `prompts/agent_prompt_forex.py`
- [ ] Create `configs/forex_config.json`
- [ ] Register BaseAgentForex in `main.py` AGENT_REGISTRY
- [ ] Add forex symbols to `tools/price_tools.py`

### Phase 2: Risk Engine (Week 2-3)
- [ ] Build `tools/forex_risk_manager.py`
- [ ] Implement lot size calculator with pip value tables
- [ ] Add challenge mode tracking (levels, wins, resets)
- [ ] Add daily loss limits and drawdown protection
- [ ] Add news event calendar integration

### Phase 3: Live Connection (Week 3-4)
- [ ] Connect to demo MT4/MT5 account
- [ ] Test order execution (buy, sell, modify, close)
- [ ] Test position tracking and reconciliation
- [ ] Verify SL/TP placement accuracy
- [ ] Handle edge cases (weekend gaps, spread spikes, requotes)

### Phase 4: AI Tuning (Week 4-8)
- [ ] Run on demo with multiple LLMs (Claude, GPT, DeepSeek)
- [ ] Compare win rates, avg pips, drawdown per model
- [ ] Tune system prompt based on trade analysis
- [ ] Implement adaptive risk sizing (reduce after losses)
- [ ] Add trailing stop logic for runners

### Phase 5: Go Live (Week 8+)
- [ ] Fund $20 live account at chosen broker
- [ ] Run challenge Mode 1 (aggressive compound)
- [ ] Monitor, log, analyze every trade
- [ ] Scale to Mode 2/3 based on proven performance
- [ ] Set up dashboard for monitoring

---

## 11. CRITICAL RISK WARNINGS

1. **This is NOT financial advice**. AI trading carries significant risk of loss.
2. **The compounding math assumes 100% win rate** - real markets have losses, slippage, spread costs, and gaps.
3. **Past backtesting performance does NOT predict live results**. Live markets have execution delays, requotes, and varying liquidity.
4. **Start with demo accounts**. Validate for weeks before risking real money.
5. **Never risk money you can't afford to lose**. The $20 challenge is designed to limit downside.
6. **Leverage amplifies both gains and losses**. 500:1 leverage means a 0.2% move wipes out 100% of a fully leveraged position.
7. **Broker selection matters**. Some brokers trade against clients (market makers). Use ECN/STP brokers.
8. **Regulatory compliance**. Check your jurisdiction's rules on automated trading and forex.

---

## 12. ESTIMATED COSTS

| Item | Monthly Cost |
|------|-------------|
| Windows VPS (2GB RAM) | $10-25 |
| Claude API (Opus, ~100 calls/day) | $50-150 |
| MetaApi (if Linux) | $0-20 |
| Broker account | $20 (one-time deposit) |
| Alpha Vantage / news API | $0-50 |
| **Total** | **$80-245/month** |

Break-even: Need to generate >$245/month in trading profits to be sustainable.

---

## 13. NEXT STEPS

If you want to proceed, I recommend:

1. **Pick a broker** that supports MT4/MT5 with micro lots and allows EAs
2. **Open a demo account** (free, unlimited practice)
3. **I build Phase 1** (the forex agent, MT4/MT5 adapter, and MCP tools)
4. **Connect to demo**, run for 2-4 weeks, measure real win rates
5. **Go live with $20** once demo shows consistent 60%+ win rate
6. **Scale up** based on proven performance

The codebase is perfectly structured for this extension. The MCP architecture means we just need to:
- Add a new agent class (mirrors crypto agent)
- Add a new trade tool (talks to MT4/MT5 instead of JSONL)
- Add a forex-specific prompt (with risk management focus)
- Add a challenge mode tracker

Everything else (LLM integration, logging, metrics) already works.
