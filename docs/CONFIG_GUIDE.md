# Configuration System Documentation

## Overview

The AI-Trader frontend uses a unified YAML configuration file (`config.yaml`) to manage all agent configurations, display settings, and data paths. The system now supports **multiple markets** (US, China A-Shares, and more) with market-specific agents, data paths, and time granularities.

## Configuration File Location

```
docs/config.yaml
```

## Multi-Market Architecture

The configuration uses a `markets` section to support different trading markets:

```yaml
markets:
  us:    # Market ID
    name: "US Market (Nasdaq-100)"
    time_granularity: "hourly"   # or "daily"
    agents: [...]                 # Market-specific agents
  cn:    # Another market
    name: "A-Shares (SSE 50)"
    time_granularity: "daily"
    agents: [...]
```

Each market can have:
- Different time granularities (hourly vs daily)
- Different data storage formats (individual files vs merged)
- Different agents with different configurations
- Different benchmarks and currencies

## Adding a New Agent to a Market

To add a new agent to a specific market, add it to that market's `agents` section:

```yaml
markets:
  us:
    agents:
      - folder: "your-agent-folder-name"      # Directory under data/agent_data/
        display_name: "Your Agent Display Name"
        icon: "./figs/your-icon.svg"
        color: "#ff6b6b"                      # Hex color for charts
```

### Example: Adding GPT-5 Turbo to US Market

```yaml
markets:
  us:
    agents:
      - folder: "gpt-5-turbo"
        display_name: "GPT-5 Turbo"
        icon: "./figs/openai.svg"
        color: "#ffbe0b"
```

The frontend will automatically:
- Look for position data at `data/agent_data/gpt-5-turbo/position/position.jsonl`
- Display it as "GPT-5 Turbo" in the US market view
- Use hourly timestamps (if market is configured for hourly)
- Apply the yellow color (#ffbe0b) in charts

## Disabling an Agent

Set `enabled: false` in the market-level configuration to disable a market entirely. To disable individual agents, simply remove them from the agents list or comment them out:

```yaml
markets:
  us:
    enabled: false  # Disables entire US market
  cn:
    agents:
      # - folder: "old-agent"  # Commented out to disable
      #   display_name: "Old Agent"
```

## Configuration Sections

### 1. Markets (`markets`)

Each market has its own complete configuration:

```yaml
markets:
  us:
    name: "US Market (Nasdaq-100)"
    subtitle: "Track how different AI models perform in Nasdaq-100 stock trading"
    data_dir: "agent_data"                              # Directory for agent data
    benchmark_file: "Adaily_prices_QQQ.json"           # Benchmark price file
    benchmark_name: "QQQ"
    benchmark_display_name: "QQQ Invesco"
    currency: "USD"
    icon: "🇺🇸"
    price_data_type: "individual"                       # or "merged"
    time_granularity: "hourly"                          # or "daily"
    enabled: true
    agents: [...]                                       # Market-specific agents
```

**Key Fields:**

- `name`: Market display name
- `data_dir`: Directory under `data/` for agent position files
- `price_data_type`:
  - `"individual"`: Each stock has its own JSON file (e.g., `daily_prices_AAPL.json`)
  - `"merged"`: All prices in one `merged.jsonl` file
- `price_data_file`: Required if `price_data_type: "merged"` (e.g., `"A_stock/merged.jsonl"`)
- `time_granularity`:
  - `"hourly"`: Timestamps include hour component (e.g., "2024-10-01 10:00")
  - `"daily"`: Timestamps are dates only (e.g., "2024-10-01")
- `benchmark_file`: Path to benchmark price data
- `currency`: Display currency (USD, CNY, etc.)

### 2. Market Agents (`markets.<market_id>.agents`)

Each market has its own list of agents:

```yaml
markets:
  us:
    agents:
      - folder: "agent-directory-name"
        display_name: "Display Name"
        icon: "./figs/icon.svg"
        color: "#hexcolor"
```

**Fields:**
- `folder`: Directory name under `data/<data_dir>/` (must match exactly)
- `display_name`: Human-readable name shown in UI
- `icon`: Path to SVG icon (relative to docs/)
- `color`: Hex color code for chart lines and UI elements

### 3. Data Paths (`data`)

Legacy configuration for backward compatibility:

```yaml
data:
  base_path: "./data"
  price_file_prefix: "daily_prices_"
  benchmark_file: "Adaily_prices_QQQ.json"
```

**Note**: Market-specific paths in the `markets` section take precedence.

### 4. Benchmark (`benchmark`)

Legacy benchmark configuration (still supported for backward compatibility):

```yaml
benchmark:
  folder: "QQQ"
  display_name: "QQQ Invesco"
  icon: "./figs/stock.svg"
  color: "#ff6b00"
  enabled: true
```

**Note**: Market-specific benchmarks (defined in `markets.<market_id>.benchmark_file`) are preferred.

### 5. Chart Settings (`chart`)

Visual settings for the asset evolution chart:

```yaml
chart:
  default_scale: "linear"      # "linear" or "logarithmic"
  max_ticks: 15                # Maximum number of x-axis labels
  point_radius: 0              # Size of data points (0 = hidden)
  point_hover_radius: 7        # Size when hovering
  border_width: 3              # Line thickness
  tension: 0.42                # Line smoothness (0-1)
```

### 5. UI Settings (`ui`)

General UI configuration:

```yaml
ui:
  initial_value: 10000           # Starting cash for all agents
  max_recent_trades: 20          # Number of trades shown in portfolio
  date_formats:
    hourly: "MM/DD HH:mm"
    daily: "YYYY-MM-DD"
```

## Available Icons

The following icons are available in `docs/figs/`:

- `claude-color.svg` - Anthropic Claude
- `deepseek.svg` - DeepSeek
- `google.svg` - Google/Gemini
- `openai.svg` - OpenAI/GPT
- `qwen.svg` - Qwen
- `stock.svg` - Generic/Default icon

## Color Recommendations

Use distinct colors for different agents to make them easy to distinguish. **Current palette** (based on agent index order):

1. **Gemini 2.5 Flash**: `#00d4ff` (Cyan Blue)
2. **Qwen3 Max**: `#00ffcc` (Cyan)
3. **DeepSeek Chat v3.1**: `#ff006e` (Hot Pink)
4. **GPT-5**: `#ffbe0b` (Yellow)
5. **Claude 3.7 Sonnet**: `#8338ec` (Purple)
6. **MiniMax M2**: `#3a86ff` (Blue)
7. **Additional colors**: `#fb5607` (Orange), `#06ffa5` (Mint)

**QQQ Benchmark**: `#ff6b00` (Orange)

## Directory Structure

The configuration supports multiple market structures:

### For US Market (Individual Price Files)

```
data/
├── agent_data/                    # US market agents (data_dir: "agent_data")
│   ├── gemini-2.5-flash/
│   │   └── position/
│   │       └── position.jsonl
│   ├── qwen3-max/
│   │   └── position/
│   │       └── position.jsonl
│   └── ...
├── daily_prices_AAPL.json        # Individual stock price files
├── daily_prices_MSFT.json
└── Adaily_prices_QQQ.json        # Benchmark

```

### For CN Market (Merged Price File)

```
data/
├── agent_data_astock/            # CN market agents (data_dir: "agent_data_astock")
│   ├── gemini-2.5-flash/
│   │   └── position/
│   │       └── position.jsonl
│   ├── qwen3-max/
│   │   └── position/
│   │       └── position.jsonl
│   └── ...
└── A_stock/
    ├── merged.jsonl              # All stock prices in one file
    └── index_daily_sse_50.json   # Benchmark
```

**Key Points:**
- Each market can have its own `data_dir` under `data/`
- US market uses `price_data_type: "individual"` with separate files per stock
- CN market uses `price_data_type: "merged"` with all prices in `merged.jsonl`
- Agent folder names must match the `folder` field in config

## Validation

The frontend will automatically:
- Check if each enabled agent's data file exists
- Skip agents that don't have data files
- Log warnings in the browser console for missing agents

## Common Use Cases

### 1. Adding a New Market

To add a new market (e.g., cryptocurrency):

```yaml
markets:
  crypto:
    name: "Crypto Market"
    subtitle: "Track how different AI models perform in cryptocurrency trading"
    data_dir: "agent_data_crypto"
    benchmark_file: "crypto/btc.json"
    benchmark_name: "BTC"
    benchmark_display_name: "Bitcoin"
    currency: "USD"
    icon: "₿"
    price_data_type: "merged"
    price_data_file: "crypto/merged.jsonl"
    time_granularity: "hourly"
    enabled: true
    agents:
      - folder: "gemini-2.5-flash"
        display_name: "Gemini 2.5 Flash"
        icon: "./figs/google.svg"
        color: "#00d4ff"
```

### 2. Adding Agents to Multiple Markets

To add the same agent to both US and CN markets:

```yaml
markets:
  us:
    agents:
      - folder: "new-agent"
        display_name: "New Agent"
        icon: "./figs/stock.svg"
        color: "#ff6b6b"
  cn:
    agents:
      - folder: "new-agent"
        display_name: "New Agent"
        icon: "./figs/stock.svg"
        color: "#ff6b6b"
```

Ensure the agent has position data in both market directories:
- `data/agent_data/new-agent/position/position.jsonl` (US)
- `data/agent_data_astock/new-agent/position/position.jsonl` (CN)

### 3. Switching Time Granularity

Change from daily to hourly timestamps for a market:

```yaml
markets:
  cn:
    time_granularity: "hourly"  # Changed from "daily"
    # ... rest of config
```

**Important**: Ensure your data timestamps match the granularity:
- Hourly: `"2024-10-01 10:00"`
- Daily: `"2024-10-01"`

### 4. Changing Data Storage Format

Switch from individual files to merged format:

```yaml
markets:
  us:
    price_data_type: "merged"                    # Changed from "individual"
    price_data_file: "US_market/merged.jsonl"   # Add this field
    # ... rest of config
```

Then consolidate all `daily_prices_*.json` files into `data/US_market/merged.jsonl`.

### 5. Changing Display Names and Colors

Just edit the agent configuration in the market:

```yaml
markets:
  us:
    agents:
      - folder: "gpt-5"
        display_name: "GPT-5 (Latest)"  # Changed display name
        icon: "./figs/openai.svg"
        color: "#00ff00"                # Changed color to green
```

## Troubleshooting

### Agent Not Appearing

1. Check that the market is `enabled: true` in config.yaml
2. Verify the agent exists in that market's `agents` list
3. Ensure the folder name matches exactly (case-sensitive)
4. Verify `position.jsonl` exists at `data/<data_dir>/{folder}/position/position.jsonl`
5. Check browser console for error messages

**Example for US market:**
- Config: `folder: "gemini-2.5-flash"`
- Expected path: `data/agent_data/gemini-2.5-flash/position/position.jsonl`

### Wrong Timestamps or Date Format

1. Check the market's `time_granularity` setting
2. Ensure position data timestamps match:
   - Hourly: `"2024-10-01 10:00"` (with hour)
   - Daily: `"2024-10-01"` (date only)
3. Check `ui.date_formats` in config.yaml matches your granularity

### Market Not Showing

1. Ensure `enabled: true` for that market
2. Verify `data_dir` exists under `data/`
3. Check that at least one agent has valid data
4. Verify benchmark file exists at the specified path

### Price Data Not Loading

For **individual** price data type:
1. Check files exist: `data/daily_prices_<SYMBOL>.json`
2. Verify file naming matches `price_file_prefix` setting

For **merged** price data type:
1. Check `price_data_file` is specified in market config
2. Verify file exists: `data/<price_data_file>`
3. Ensure JSONL format: one JSON object per line

### Configuration Not Loading

1. Ensure `config.yaml` is valid YAML syntax
2. Check browser console for YAML parsing errors
3. Verify the config.yaml file is in the `docs/` directory

## Best Practices

1. **Organize agents by market** - Keep market-specific agents in their respective `agents` lists
2. **Use consistent naming** across markets for the same agent (e.g., "gemini-2.5-flash" in both US and CN)
3. **Match time granularity to data** - Ensure timestamps in position files match the market's `time_granularity`
4. **Choose distinct colors** per agent (not per market) for consistency
5. **Add comments** for temporary changes:
   ```yaml
   markets:
     us:
       # enabled: false  # Temporarily disabled for testing CN market
   ```
6. **Test after changes** by reloading the page and checking:
   - Market selector shows all enabled markets
   - Agents appear with correct colors
   - Browser console shows no errors
7. **Document custom markets** if adding new ones:
   ```yaml
   # crypto:  # TODO: Enable when crypto data is ready
   #   name: "Crypto Market"
   #   enabled: false
   ```

## Migration from Legacy Config

### Old Structure (Single Market)

```yaml
agents:
  - folder: "gemini-2.5-flash"
    display_name: "Gemini 2.5 Flash"
    enabled: true
```

### New Structure (Multi-Market)

```yaml
markets:
  us:
    agents:
      - folder: "gemini-2.5-flash"
        display_name: "Gemini 2.5 Flash"
  cn:
    agents:
      - folder: "gemini-2.5-flash"
        display_name: "Gemini 2.5 Flash"
```

**Benefits:**
- Same agent can have different configurations per market
- Independent data directories and benchmarks per market
- Easy to add new markets without affecting existing ones
- Supports different time granularities (hourly vs daily)

## Advanced Configuration

### Market-Specific Agent Names

You can use different display names for the same agent in different markets:

```yaml
markets:
  us:
    agents:
      - folder: "gemini-2.5-flash"
        display_name: "Gemini 2.5 Flash (US)"
  cn:
    agents:
      - folder: "gemini-2.5-flash"
        display_name: "Gemini 2.5 Flash (CN)"
```

### Mixed Time Granularities

Different markets can use different time granularities:

```yaml
markets:
  us:
    time_granularity: "hourly"   # Intraday trading
  cn:
    time_granularity: "daily"    # End-of-day positions
```

### Conditional Market Enabling

Enable markets based on data availability:

```yaml
markets:
  us:
    enabled: true               # Production ready
  cn:
    enabled: true               # Production ready
  crypto:
    enabled: false              # Not yet ready
```
