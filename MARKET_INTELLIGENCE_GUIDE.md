# Market Intelligence System Guide

## Overview

The **Market Intelligence System** provides trading agents with curated, up-to-date narratives about macro market conditions. Instead of agents searching for news on every topic every day, a dedicated **Market Intelligence Agent** maintains concise summaries across 5 key categories:

1. 📊 **Federal Reserve & Monetary Policy**
2. 🌍 **Global Economic Conditions**
3. 📈 **Sector Trends & Rotation**
4. 📅 **Major Market Events**
5. 🌐 **Geopolitical Factors**

This provides **macro context** that helps trading agents make better decisions without information overload.

## Why This Matters

### Without Intelligence System
```
Trading Agent (every day):
- Searches "Fed interest rates" → 1000 results
- Searches "tech sector trends" → 1000 results
- Searches "global economy" → 1000 results
- Spends 10+ reasoning steps just gathering macro context
- Information is scattered, redundant, overwhelming
```

### With Intelligence System
```
Trading Agent receives:
=== MARKET INTELLIGENCE ===
Federal Reserve & Monetary Policy:
  • Fed holds rates at 5.25-5.5% (2025-10-01)

Global Economic Conditions:
  • US GDP grows 2.8%, inflation moderates to 3.2% (2025-10-01)

[... concise, curated narratives for all 5 categories]

Agent can now focus on:
- Stock-specific research
- Portfolio decisions
- Trading execution
```

## Architecture

### Components

1. **MarketIntelligence** (`tools/market_intelligence.py`)
   - Storage and retrieval system
   - Manages intelligence database
   - Builds formatted context for agents

2. **MarketIntelligenceAgent** (`agent/market_intelligence_agent/`)
   - Dedicated agent that curates intelligence
   - Searches news across categories
   - Synthesizes into concise narratives
   - Updates intelligence database

3. **Integration** (automatic)
   - Enhanced agents automatically receive intelligence context
   - Included in system prompts
   - No configuration needed

### Data Flow

```
1. Market Intelligence Agent (runs weekly/as needed)
   ├── Searches news: "Fed policy", "GDP data", "sector rotation"
   ├── Synthesizes findings
   └── Updates intelligence database

2. Intelligence Database (data/market_intelligence/intelligence.jsonl)
   ├── Stores narratives by category and date
   ├── Maintains importance scores
   └── Keeps history for 30+ days

3. Trading Agents (daily)
   ├── Enhanced prompt system loads intelligence
   ├── Receives curated narratives
   └── Makes informed decisions with macro context
```

## Intelligence Categories

### 1. Federal Reserve & Monetary Policy

**What to track:**
- Interest rate decisions and guidance
- Inflation outlook and targets
- Fed commentary and policy shifts
- Quantitative tightening/easing

**Example:**
```
Summary: Fed maintains rates at 5.25-5.5% with hawkish tone on inflation
Details: At the September FOMC meeting, the Federal Reserve held rates steady
while signaling ongoing concern about persistent inflation. Chair Powell indicated
the committee is prepared to raise rates further if needed. Markets now pricing
in potential cuts delayed to Q2 2025.
Importance: 9/10
```

### 2. Global Economic Conditions

**What to track:**
- GDP growth rates
- Employment and wages
- Inflation metrics (CPI, PCE)
- Consumer confidence
- International economic trends

**Example:**
```
Summary: US GDP growth robust at 2.8% while inflation moderates to 3.2%
Details: Q3 GDP came in at 2.8% annualized, beating expectations. Consumer
spending remains resilient. Core PCE inflation declined to 3.2% from 4.1%,
showing progress toward the Fed's 2% target. Labor markets tight but wage
growth moderating.
Importance: 8/10
```

### 3. Sector Trends & Rotation

**What to track:**
- Sector performance (tech, energy, healthcare, etc.)
- Rotation patterns
- Industry-specific developments
- Thematic trends (AI, cloud, EV, etc.)

**Example:**
```
Summary: AI and semiconductor stocks lead; energy sector under pressure
Details: Technology sector continues outperforming driven by AI enthusiasm.
NVDA, AMD, AVGO seeing strong datacenter demand. Energy sector facing headwinds
from oil price decline to $75/barrel. Rotation out of value into growth accelerating.
Importance: 8/10
```

### 4. Major Market Events

**What to track:**
- Earnings seasons and trends
- Product launches
- Regulatory changes
- M&A activity
- Corporate actions

**Example:**
```
Summary: Q3 earnings beat expectations led by tech giants
Details: 75% of S&P 500 companies beating estimates. Mega-cap tech (MSFT, GOOGL,
NVDA) reporting strong AI revenue growth. Retail earnings mixed as consumers
become selective. Forward guidance cautiously optimistic for Q4.
Importance: 7/10
```

### 5. Geopolitical Factors

**What to track:**
- Trade policy and tariffs
- International conflicts
- Supply chain disruptions
- Regulatory changes
- Currency movements

**Example:**
```
Summary: US-China tech tensions persist; Europe energy challenges
Details: Ongoing semiconductor export restrictions affecting supply chains.
US expanding controls on advanced chip equipment to China. European economies
managing energy transition. Markets monitoring Middle East oil supply risks.
Importance: 6/10
```

## Usage

### Setup (One-time)

No setup needed! Intelligence system is automatically integrated.

**Optional**: Seed initial intelligence
```bash
python scripts/update_market_intelligence.py seed 2025-10-01
```

### Update Intelligence

#### Option 1: Single Date Update
```bash
python scripts/update_market_intelligence.py update --date 2025-10-15
```

The Market Intelligence Agent will:
1. Search news for all 5 categories
2. Synthesize findings
3. Update intelligence database
4. Take ~2-3 minutes

#### Option 2: Batch Update (Weekly recommended)
```bash
python scripts/update_market_intelligence.py update --date-range 2025-10-01 2025-10-31 --frequency 7
```

Updates intelligence weekly throughout the month.

#### Option 3: Show Current Intelligence
```bash
python scripts/update_market_intelligence.py show 2025-10-15
```

Displays current intelligence for review.

### Integration with Trading Agents

**Automatic!** Enhanced trading agents receive intelligence context in their prompts.

Example from EnhancedClaudeSDKAgent:
```
=== MARKET INTELLIGENCE ===
As of 2025-10-15

Federal Reserve & Monetary Policy:
  • Fed maintains rates at 5.25-5.5% (2025-10-01)
    At the September FOMC meeting, the Federal Reserve held...

Global Economic Conditions:
  • US GDP grows 2.8%, inflation moderates (2025-10-01)
    Q3 GDP came in strong with consumer spending resilient...

[... continues for all categories]
```

Agents use this to inform decisions:
- "Given Fed's hawkish stance, avoiding rate-sensitive sectors"
- "Strong GDP supports tech growth stocks"
- "Semiconductor sector momentum aligns with AI trends"

## Workflow Recommendations

### For Backtesting

**Before running backtest:**

```bash
# 1. Seed initial intelligence for your start date
python scripts/update_market_intelligence.py seed 2025-10-01

# 2. Update intelligence weekly throughout backtest period
python scripts/update_market_intelligence.py update \
  --date-range 2025-10-01 2025-12-31 \
  --frequency 7

# 3. Run your backtest
python main.py configs/enhanced_claude_sdk_config.json
```

**Why weekly?**
- Balance between current information and API costs
- Major macro shifts don't happen daily
- Gives agents stable context for decision-making

### For Live Trading

**Setup cron job:**
```bash
# Update intelligence every Monday at 6 AM
0 6 * * 1 cd /path/to/simply-trading && python scripts/update_market_intelligence.py update --date $(date +%Y-%m-%d)
```

### Importance Scoring Guide

Use this to prioritize intelligence:

| Score | Level | Examples |
|-------|-------|----------|
| 10 | **Market-moving** | Fed rate change, major crisis, war |
| 8-9 | **Highly significant** | Strong GDP, sector rotation, major earnings |
| 6-7 | **Important** | Earnings trends, policy shifts, tech breakthroughs |
| 4-5 | **Notable** | Individual stock news, minor data points |
| 1-3 | **Background** | Long-term trends, contextual information |

**Rule**: Focus updates on importance 6+ to avoid clutter.

## Examples

### Example 1: Fed Rate Decision

```python
# Market Intelligence Agent discovers Fed decision
await update_fed_policy({
    "summary": "Fed cuts rates 25bp to 5.00-5.25%, signals pause",
    "details": (
        "The Federal Reserve cut rates by 25 basis points citing moderating "
        "inflation and slowing employment growth. This is the first cut in "
        "16 months. Chair Powell indicated the committee will monitor data "
        "closely before further moves, suggesting a pause ahead."
    ),
    "importance": 10  # Market-moving
})
```

**Impact on trading agents:**
- Agents now aware of easing cycle
- May favor growth stocks over bonds
- Understand rate-sensitive sector implications

### Example 2: Earnings Season

```python
await update_major_events({
    "summary": "Tech earnings exceed expectations; AI revenue surging",
    "details": (
        "Q3 earnings from MSFT, GOOGL, META beat estimates with AI-driven "
        "cloud revenue up 30%+ YoY. Management guidance optimistic on "
        "datacenter buildouts continuing into 2026. This validates AI "
        "investment thesis and supports premium valuations."
    ),
    "importance": 8  # Highly significant
})
```

**Impact:**
- Agents have context for tech stock valuations
- Understand why NVDA/AMD seeing strong demand
- Can reference earnings strength in trading rationale

### Example 3: Sector Rotation

```python
await update_sector_trends({
    "summary": "Rotation from growth to value as yields rise",
    "details": (
        "10-year Treasury yield climbing to 4.8% triggering rotation out "
        "of high-multiple tech stocks into value sectors (financials, energy). "
        "NASDAQ underperforming S&P 500 by 2% this week. Investors seeking "
        "yield and de-risking growth exposure."
    ),
    "importance": 7  # Important
})
```

**Impact:**
- Agents understand current market regime
- May reduce tech exposure
- Consider defensive positioning

## Best Practices

### 1. Conciseness is Key

**❌ Too verbose:**
```
"The Federal Reserve met on September 20th and after extensive deliberation
among the committee members, considering various economic indicators including
the consumer price index, the personal consumption expenditures price index,
unemployment figures, and GDP growth rates, as well as reviewing commentary
from regional Fed presidents and analyzing forward-looking market indicators..."
```

**✅ Concise:**
```
Summary: Fed holds rates at 5.25-5.5% citing persistent inflation
Details: September FOMC held rates steady. Chair Powell indicated concern
about sticky inflation and willingness to raise further if needed. Markets
now expect rates higher for longer through Q1 2025.
```

### 2. Focus on Tradeable Insights

**❌ Not actionable:**
```
"The global economy faces many challenges including demographic shifts,
technological disruption, and climate change impacts."
```

**✅ Actionable:**
```
"US GDP growth at 2.8% supports continued corporate earnings growth,
particularly in consumer discretionary and technology sectors."
```

### 3. Update When Significant

**Don't update daily** unless major news:
- Daily: ❌ "Stock market up 0.3%"
- Weekly: ✅ "Tech sector outperforming, AI momentum continues"
- Event-driven: ✅ "Fed cuts rates 50bp emergency action"

### 4. Maintain Recency

Intelligence older than 30 days is automatically filtered out. Keep narratives current:

- Update Fed policy after FOMC meetings (~8x/year)
- Update economy after major data releases (GDP, jobs, CPI)
- Update sectors weekly or when rotation visible
- Update events as they occur (earnings, M&A, etc.)

## API Costs

Market Intelligence Agent costs per update:

- **Single category search + synthesis**: ~$0.05-0.10
- **Full 5-category update**: ~$0.25-0.50
- **Weekly updates for 3 months**: ~$5-10 total

**ROI**: Trading agents get better context for ~$5-10, vs each agent searching separately costing $50-100+.

## Troubleshooting

### "No intelligence available"

**Solution**: Seed initial intelligence
```bash
python scripts/update_market_intelligence.py seed 2025-10-01
```

### Intelligence seems outdated

**Solution**: Run update
```bash
python scripts/update_market_intelligence.py update --date $(date +%Y-%m-%d)
```

### Agent ignoring intelligence

**Check**: Enhanced agents only. Base agents don't use intelligence.

**Verify** intelligence is loaded:
```bash
python scripts/update_market_intelligence.py show 2025-10-15
```

### Intelligence too verbose

**Edit** `max_length` in `build_intelligence_context()`:
```python
intel.build_intelligence_context(date, max_length=1000)  # Shorter
```

## Advanced: Custom Intelligence Categories

Want to add custom categories?

**1. Edit `tools/market_intelligence.py`:**
```python
CATEGORIES = [
    "fed_policy",
    "global_economy",
    "sector_trends",
    "major_events",
    "geopolitical",
    "crypto_markets",  # NEW
    "commodities"      # NEW
]
```

**2. Add tools in `market_intelligence_agent.py`:**
```python
@tool(name="update_crypto_markets", ...)
async def update_crypto_markets(args: Dict) -> Dict:
    # Implementation
```

**3. Update agent system prompt** to search new categories.

## Summary

**Market Intelligence System** = Curated macro context for trading agents

**Benefits:**
✅ Agents get macro context without excessive searching
✅ Information is curated, concise, and current
✅ Reduces API costs and reasoning steps
✅ Improves decision quality with broader perspective
✅ Maintains narratives across backtesting period

**Usage:**
```bash
# Seed once
python scripts/update_market_intelligence.py seed 2025-10-01

# Update weekly
python scripts/update_market_intelligence.py update \
  --date-range 2025-10-01 2025-12-31 --frequency 7

# Agents automatically receive context - no config needed!
```

**Cost:** ~$5-10 for 3 months of weekly updates

**Impact:** Trading agents make better macro-informed decisions

---

**Start using market intelligence today!** 📰📊🚀
