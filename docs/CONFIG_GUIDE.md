# Configuration System Documentation

## Overview

The AI-Trader frontend uses a unified YAML configuration file (`config.yaml`) to manage all agent configurations, display settings, and data paths. This makes maintenance much easier - you only need to edit one file to add new agents, change colors, or update settings.

## Configuration File Location

```
docs/config.yaml
```

## Adding a New Agent

To add a new agent, simply add a new entry to the `agents` section in `config.yaml`:

```yaml
agents:
  - folder: "your-agent-folder-name"      # The directory name under data/agent_data/
    display_name: "Your Agent Display Name"  # How it appears in the UI
    icon: "./figs/your-icon.svg"          # Path to the icon file
    color: "#ff6b6b"                      # Hex color code for charts
    enabled: true                          # Set to false to temporarily disable
```

### Example: Adding a New GPT-5 Agent

```yaml
agents:
  - folder: "test-gpt-5-turbo"
    display_name: "GPT-5 Turbo"
    icon: "./figs/openai.svg"
    color: "#10a37f"
    enabled: true
```

That's it! The frontend will automatically:
- Look for position data at `data/agent_data/test-gpt-5-turbo/position/position.jsonl`
- Display it as "GPT-5 Turbo" in the UI
- Use the OpenAI icon and green color
- Include it in all charts and analytics

## Disabling an Agent

To temporarily disable an agent without deleting its configuration:

```yaml
agents:
  - folder: "old-agent"
    display_name: "Old Agent"
    icon: "./figs/stock.svg"
    color: "#00d4ff"
    enabled: false  # Agent will be skipped
```

## Configuration Sections

### 1. Data Paths (`data`)

```yaml
data:
  base_path: "./data"                    # Base directory for all data
  price_file_prefix: "daily_prices_"     # Prefix for stock price files
  benchmark_file: "Adaily_prices_QQQ.json"  # Benchmark data file
```

### 2. Agents (`agents`)

List of all trading agents with their display configurations:

```yaml
agents:
  - folder: "agent-directory-name"
    display_name: "Display Name"
    icon: "./figs/icon.svg"
    color: "#hexcolor"
    enabled: true
```

**Fields:**
- `folder`: Directory name under `data/agent_data/` (must match exactly)
- `display_name`: Human-readable name shown in UI
- `icon`: Path to SVG icon (relative to docs/)
- `color`: Hex color code for chart lines and UI elements
- `enabled`: Boolean to enable/disable the agent

### 3. Benchmark (`benchmark`)

Configuration for the benchmark comparison (e.g., QQQ):

```yaml
benchmark:
  folder: "QQQ"
  display_name: "QQQ Invesco"
  icon: "./figs/stock.svg"
  color: "#ff6b00"
  enabled: true
```

### 4. Chart Settings (`chart`)

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

Use distinct colors for different agents to make them easy to distinguish:

- **Claude**: `#cc785c` (orange)
- **DeepSeek**: `#4a90e2` (blue)
- **Gemini**: `#8A2BE2` (purple)
- **GPT**: `#10a37f` (green)
- **Qwen**: `#0066ff` (bright blue)
- **MiniMax**: `#ff6b6b` (red)
- **QQQ Benchmark**: `#ff6b00` (orange)

## Directory Structure

The configuration expects the following directory structure:

```
data/
├── agent_data/
│   ├── agent-folder-1/
│   │   └── position/
│   │       └── position.jsonl
│   ├── agent-folder-2/
│   │   └── position/
│   │       └── position.jsonl
│   └── ...
├── daily_prices_AAPL.json
├── daily_prices_MSFT.json
└── Adaily_prices_QQQ.json
```

## Validation

The frontend will automatically:
- Check if each enabled agent's data file exists
- Skip agents that don't have data files
- Log warnings in the browser console for missing agents

## Common Use Cases

### 1. Adding a Batch of New Agents

```yaml
agents:
  # Existing agents...

  # New batch
  - folder: "new-agent-1"
    display_name: "New Agent 1"
    icon: "./figs/stock.svg"
    color: "#ff6b6b"
    enabled: true

  - folder: "new-agent-2"
    display_name: "New Agent 2"
    icon: "./figs/stock.svg"
    color: "#00d4ff"
    enabled: true
```

### 2. Changing Display Names

Just edit the `display_name` field - no code changes needed:

```yaml
- folder: "test-gpt-4.1"
  display_name: "GPT-4.1 (Updated)"  # Changed from "GPT-4.1"
  icon: "./figs/openai.svg"
  color: "#10a37f"
  enabled: true
```

### 3. Disabling Old Agents

Set `enabled: false` for agents you want to hide:

```yaml
- folder: "old-experiment"
  display_name: "Old Experiment"
  icon: "./figs/stock.svg"
  color: "#cccccc"
  enabled: false  # Will not appear in UI
```

### 4. Changing Chart Colors

Update the `color` field with a new hex code:

```yaml
- folder: "test-claude-3.7-sonnet"
  display_name: "Claude 3.7 Sonnet"
  icon: "./figs/claude-color.svg"
  color: "#ff0000"  # Changed to red
  enabled: true
```

## Troubleshooting

### Agent Not Appearing

1. Check that `enabled: true` in config.yaml
2. Verify the folder name matches exactly
3. Ensure `position.jsonl` exists at `data/agent_data/{folder}/position/position.jsonl`
4. Check browser console for error messages

### Wrong Colors or Icons

1. Verify the hex color code is valid (6 characters after #)
2. Check that the icon file exists at the specified path
3. Clear browser cache and reload

### Configuration Not Loading

1. Ensure `config.yaml` is valid YAML syntax
2. Check browser console for YAML parsing errors
3. Verify the config.yaml file is in the `docs/` directory

## Best Practices

1. **Keep enabled agents at the top** of the agents list for easier management
2. **Use consistent naming** for similar agents (e.g., "test-" prefix for test runs)
3. **Choose distinct colors** to make agents easy to distinguish in charts
4. **Add comments** in YAML to document temporary changes:
   ```yaml
   # Temporarily disabled for performance testing
   - folder: "heavy-agent"
     enabled: false
   ```
5. **Test after changes** by reloading the page and checking the browser console

## Migration from Hardcoded Config

The old system required editing JavaScript files to add agents. Now you can:

**Old way** (editing data-loader.js):
```javascript
const names = {
    'test-gpt-4.1': 'GPT-4.1',
    // ... add more here
};
```

**New way** (editing config.yaml):
```yaml
- folder: "test-gpt-4.1"
  display_name: "GPT-4.1"
  icon: "./figs/openai.svg"
  color: "#10a37f"
  enabled: true
```

No code changes needed! Just edit the YAML file and reload the page.
