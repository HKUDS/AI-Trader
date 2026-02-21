# Frontend Caching System

## Overview

The AI-Trader frontend includes a **two-tier caching system** designed to dramatically improve page load times by pre-computing and caching expensive calculations. The system supports multiple markets including **US stocks**, **A-shares (daily)**, and **A-shares (hourly)** with seamless 1D/1H toggle functionality.

### Performance Improvements

- **Initial Load**: ~100-500ms (previously 5-10 seconds)
- **Subsequent Loads**: ~50-100ms (cached in browser)
- **Market Switching**: Instant (no recalculation needed)
- **1D/1H Toggle**: Instant switching between daily and hourly views

## How It Works

### Tier 1: Pre-computed Static Cache

A Python script (`scripts/precompute_frontend_cache.py`) generates static JSON files containing all calculated metrics:

- **Output Files**:
  - `docs/data/us_cache.json` - US market data (hourly timestamps)
  - `docs/data/cn_cache.json` - A-share market data (daily aggregation)
  - `docs/data/cn_hour_cache.json` - A-share market data (hourly timestamps)

- **Contents**:
  - Version hash (manual prefix + file timestamp hash)
  - All agents' asset histories with calculated values
  - Benchmark data (QQQ/SSE 50) aligned with agent date ranges
  - Pre-calculated returns and metrics

### Tier 2: Browser localStorage Cache

The frontend (`assets/js/cache-manager.js`) implements smart caching with per-market storage:

1. **First Load**: Fetches pre-computed cache from server for the active market
   - Uses cache-busting headers to bypass browser HTTP cache
   - Ensures latest version is always checked from server
2. **Saves to localStorage**: Stores each market's cache separately (us, cn, cn_hour)
3. **Version Checking**: Auto-invalidates when data changes (version mismatch)
4. **Graceful Degradation**: Falls back to live calculation if cache unavailable
5. **Market-Specific**: Each market (us, cn, cn_hour) has its own cache entry

### 1D/1H Toggle Support

The A-shares market includes a 1D/1H toggle that switches between daily and hourly views:

- **1D (Daily)**: Loads `cn_cache.json` - 35+ daily data points aggregated from hourly positions
- **1H (Hourly)**: Loads `cn_hour_cache.json` - 120+ hourly data points (Oct 9 08:30 to Nov 19 14:00)
- **Seamless Switching**: JavaScript switches between `cn` and `cn_hour` market IDs
- **Both Cached**: Both caches are pre-generated even though `cn_hour` has `enabled: false` in config
- **No Recalculation**: Toggle is instant as both caches are pre-computed

## Usage

### For Developers

#### After Updating Trading Data

Run this command to regenerate **all three cache files**:

```bash
bash scripts/regenerate_cache.sh
```

Or manually:

```bash
python3 scripts/precompute_frontend_cache.py
```

This will generate:
- `docs/data/us_cache.json` (~3.6 MB)
- `docs/data/cn_cache.json` (~1.6 MB)
- `docs/data/cn_hour_cache.json` (~1.5 MB)

#### Commit the Cache Files

For GitHub Pages deployment, commit the generated cache files:

```bash
git add docs/data/us_cache.json docs/data/cn_cache.json docs/data/cn_hour_cache.json
git commit -m "Update frontend cache"
git push
```

#### Force Cache Invalidation

If you make structural changes to the data format, increment the `CACHE_FORMAT_VERSION` in `scripts/precompute_frontend_cache.py`:

```python
# Line ~604 in precompute_frontend_cache.py
CACHE_FORMAT_VERSION = 'v4'  # Increment this when changing data structure
```

This forces all browser caches to invalidate and reload.

### For Users

**No action required!** The caching system works automatically:

1. First visit: Loads pre-computed cache (~100ms)
2. Subsequent visits: Uses browser cache (~50ms)
3. After data updates: Automatically detects new version and refreshes

## Cache Management

### Check Cache Status

Open browser console and run:

```javascript
window.dataLoader.cacheManager.getStats()
```

Output:
```javascript
{
  localCaches: [
    {
      market: 'us',
      version: 'a1b2c3d4e5f6',
      age: '2 hours',
      timestamp: '2025-11-19T08:30:00.000Z'
    }
  ],
  totalSize: '245.67 KB'
}
```

### Clear Browser Cache

To force a fresh load, run in console:

```javascript
window.dataLoader.cacheManager.clearAllLocalCaches()
```

Then refresh the page.

### Disable Caching (for debugging)

Temporarily rename or delete the cache files:

```bash
mv docs/data/us_cache.json docs/data/us_cache.json.bak
mv docs/data/cn_cache.json docs/data/cn_cache.json.bak
```

The frontend will automatically fall back to live calculation.

## Technical Details

### Multi-Market Architecture

The caching system is designed to support multiple markets with different time granularities:

**Market Configuration** (`docs/config.yaml`):
```yaml
markets:
  us:
    time_granularity: "hourly"
    price_data_type: "individual"
    # ... US-specific settings

  cn:
    time_granularity: "daily"
    price_data_type: "merged"
    price_data_file: "A_stock/merged.jsonl"
    # ... CN daily settings

  cn_hour:
    time_granularity: "hourly"
    price_data_type: "merged"
    price_data_file: "A_stock/merged_hourly.jsonl"
    enabled: false  # Hidden from UI, toggled by 1D/1H button
    # ... CN hourly settings
```

### Cache Generation Algorithm

**Key Functions** in `scripts/precompute_frontend_cache.py`:

1. **`load_price_data_cn(market_config)`** (lines 100-131)
   - Dynamically loads price data based on market config
   - For `time_granularity: "hourly"`: Loads from `merged_hourly.jsonl` with `Time Series (60min)` key
   - For `time_granularity: "daily"`: Loads from `merged.jsonl` with `Time Series (Daily)` key
   - Returns dict: `{symbol: {timestamp: {price_data}}}`

2. **`get_closing_price(symbol, date, price_data, market)`** (lines 134-187)
   - **Critical for hourly data**: Must handle exact timestamp matching
   - For CN market with hourly timestamps:
     1. Try exact timestamp match first (e.g., `2025-11-19 10:30:00`)
     2. Check for N/A values and skip them
     3. Fall back to daily date matching if no hourly data
     4. For prefix matches, only use timestamps ≤ requested time (not future data)
   - **Anti-look-ahead protection**: Never returns prices from after requested timestamp

3. **`process_agent_data_cn(agent_config, market_config, price_cache)`** (lines 241-375)
   - Detects if data is hourly vs daily based on timestamp format
   - **Key logic**:
     ```python
     preserve_hourly = market_config.get('time_granularity') == 'hourly' and is_hourly_data
     ```
   - If `preserve_hourly == True`:
     - Keeps full timestamps as keys (`2025-11-19 10:30:00`)
     - Returns all hourly data points without date filling
     - No weekend skipping (markets may have different trading hours)
   - If `preserve_hourly == False`:
     - Aggregates to daily keys (`2025-11-19`)
     - Fills gaps with last known position
     - Skips weekends

4. **`process_benchmark_cn(market_config, agents_data)`** (lines 467-555)
   - **Critical fix**: Must extract initial value from first agent to match scaling
   - **Date range alignment**: Filters benchmark data to match agent date ranges
   - Prevents benchmark mismatch (e.g., ¥10,000 baseline vs ¥100,000 agents)

### Version Detection

The cache version is computed as:

```python
CACHE_FORMAT_VERSION = 'v3'  # Manual prefix for structural changes
file_hash = md5(position_file_timestamps)  # Auto-generated from file mtimes
cache_version = f"{CACHE_FORMAT_VERSION}_{file_hash}"
```

**Two-part versioning**:
- **Manual prefix** (`v3`): Increment when changing data structure or calculation logic
- **File hash**: Auto-updates when position files change

This ensures:
- Browser caches invalidate when data structure changes
- Auto-invalidation when trading data updates
- No manual cache clearing needed for data updates

### Cache Expiration

- **localStorage cache**: Auto-expires after 7 days
- **Server cache**: Never expires (must be regenerated manually)

### Fallback Strategy

The system has three fallback levels:

1. **localStorage cache** (fastest): Instant load from browser storage (~50ms)
2. **Server cache**: Single JSON file fetch from `/data/{market}_cache.json` (~100-500ms)
3. **Live calculation**: Original slow path (only if cache unavailable, 5-10 seconds)

### Data Flow

```
Page Load (e.g., A-Shares 1D view)
    ↓
Check localStorage for 'cn' market
    ↓
├─ Hit (version matches) → Use cached data ✓
└─ Miss/Outdated
       ↓
   Fetch /data/cn_cache.json
       ↓
   ├─ Available → Save to localStorage → Use cached data ✓
   └─ Unavailable
          ↓
      Live calculation (slow path)

User clicks "1H" toggle
    ↓
Check localStorage for 'cn_hour' market
    ↓
├─ Hit → Use cached data ✓
└─ Miss
       ↓
   Fetch /data/cn_hour_cache.json
       ↓
   Save to localStorage → Use cached data ✓
```

### Common Pitfalls and Solutions

#### 1. Hourly Data Showing as Daily (Missing Timestamps)

**Symptom**: Cache shows only ~30 daily points instead of 120 hourly points

**Cause**: `time_granularity` not set to `"hourly"` in market config, or `preserve_hourly` logic not triggered

**Solution**:
```yaml
# In docs/config.yaml
cn_hour:
  time_granularity: "hourly"  # Must be set!
  price_data_file: "A_stock/merged_hourly.jsonl"
```

#### 2. Prices Returning 0.0 or None for Valid Timestamps

**Symptom**: Asset values return None, data points missing from cache

**Cause**: Price lookup logic not handling hourly timestamps correctly

**Common issues**:
- `load_price_data_cn()` loading daily keys instead of hourly keys
- `get_closing_price()` not trying exact match before prefix matching
- Taking last timestamp of day when looking for earlier times (look-ahead!)

**Solution**: Ensure `get_closing_price()` tries exact match first:
```python
# Try exact match first (for hourly data)
if date in prices:
    price_value = prices[date].get('4. close') or prices[date].get('4. sell price', 0)
    if price_value and price_value != 'N/A':
        return float(price_value)
```

#### 3. Benchmark Baseline 10x Too High/Low

**Symptom**: Chart shows benchmark at ¥10,000 while agents at ¥100,000 (or vice versa)

**Cause**: Benchmark using hardcoded `initial_value` instead of matching agent values

**Solution**: Extract initial value from first agent:
```python
# In process_benchmark_cn/us()
initial_value = 100000  # Default
if agents_data:
    for agent_data in agents_data.values():
        if agent_data.get('assetHistory'):
            initial_value = agent_data['assetHistory'][0]['value']
            break
```

#### 4. Browser Cache Not Invalidating After Updates

**Symptom**: Generated new cache file but browser still shows old data

**Root Cause**: Browser's HTTP cache serving stale `*_cache.json` files

**Solution**: Added cache-busting to `cache-manager.js` (lines 126-136):
```javascript
// Add cache-busting to prevent browser HTTP cache from serving stale files
const timestamp = Date.now();
const response = await fetch(`./data/${market}_cache.json?v=${timestamp}`, {
    cache: 'no-store',
    headers: {
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0'
    }
});
```

This ensures the browser always checks the server for the latest version instead of serving cached files.

#### 5. Incomplete Data for Latest Trading Day

**Symptom**: Cache missing today's data even though position files have it

**Cause**: Price data incomplete (N/A values) for latest timestamps

**Solution**: Script correctly filters out incomplete data. Check price data:
```bash
# Check which timestamps have complete data
python3 -c "
import json
from pathlib import Path

# Load price file and check for N/A values
with open('docs/data/A_stock/merged_hourly.jsonl') as f:
    for line in f:
        data = json.loads(line)
        symbol = data['Meta Data']['2. Symbol']
        ts = data['Time Series (60min)']
        # Check Nov 19 timestamps
        for timestamp in ['2025-11-19 10:30:00', '2025-11-19 15:00:00']:
            if timestamp in ts:
                price = ts[timestamp].get('4. sell price')
                if not price or price == 'N/A':
                    print(f'{symbol} @ {timestamp}: MISSING')
"
```

#### 6. Agent Count Mismatch Between Cache and Live

**Symptom**: Cached view shows 7 agents, live view shows 8 agents

**Cause**: Agents missing explicit `enabled: true` in config.yaml

**Solution**: Add `enabled: true` to all agent configs:
```yaml
agents:
  - folder: "agent-name"
    display_name: "Agent Name"
    enabled: true  # Explicit is better than implicit!
```

## File Structure

```
AI-Trader/
├── scripts/
│   ├── precompute_frontend_cache.py   # Cache generation script (655 lines)
│   │   ├── load_price_data_cn()       # Loads price data for CN markets
│   │   ├── get_closing_price()        # Price lookup with hourly/daily logic
│   │   ├── calculate_asset_value()    # Computes portfolio value
│   │   ├── process_agent_data_cn()    # Processes CN agent data
│   │   ├── process_benchmark_cn()     # Processes SSE 50 benchmark
│   │   └── generate_cache_for_market() # Main cache generation
│   └── regenerate_cache.sh            # Helper script to regenerate all caches
├── docs/
│   ├── config.yaml                    # Market and agent configurations
│   ├── data/
│   │   ├── us_cache.json              # US market cache (~3.6 MB)
│   │   ├── cn_cache.json              # A-share daily cache (~1.6 MB)
│   │   ├── cn_hour_cache.json         # A-share hourly cache (~1.5 MB)
│   │   ├── A_stock/
│   │   │   ├── merged.jsonl           # Daily price data
│   │   │   └── merged_hourly.jsonl    # Hourly price data
│   │   └── agent_data_astock_hour/
│   │       └── {agent}/position/      # Agent position files
│   └── assets/js/
│       ├── cache-manager.js           # Cache management (localStorage)
│       ├── data-loader.js             # Modified to use caching
│       └── config-loader.js           # Loads config.yaml
└── docs/CACHING.md                    # This documentation file
```

## Troubleshooting

### Cache Not Loading

1. **Check browser console for errors**:
   - Look for `[CacheManager]` log messages
   - Check for fetch errors on `*_cache.json` files

2. **Verify cache files exist**:
   ```bash
   ls -lh docs/data/*_cache.json
   # Should show:
   # us_cache.json (~3.6 MB)
   # cn_cache.json (~1.6 MB)
   # cn_hour_cache.json (~1.5 MB)
   ```

3. **Check file contents**:
   ```bash
   head -20 docs/data/cn_hour_cache.json | jq '.version, .market'
   # Should show: "v3_a1d195d1bc9e", "cn_hour"
   ```

4. **Clear browser cache and reload**:
   - Console: `window.dataLoader.cacheManager.clearAllLocalCaches()`
   - Hard refresh: Ctrl+Shift+R (Cmd+Shift+R on Mac)

### Stale Data After Update

1. **Regenerate cache with version bump**:
   ```python
   # Edit scripts/precompute_frontend_cache.py
   CACHE_FORMAT_VERSION = 'v4'  # Increment!
   ```

2. **Run regeneration**:
   ```bash
   python3 scripts/precompute_frontend_cache.py
   ```

3. **Verify new version**:
   ```bash
   jq '.version' docs/data/cn_hour_cache.json
   # Should show: "v4_a1d195d1bc9e" (new prefix)
   ```

4. **Clear browser cache**:
   ```javascript
   // In browser console
   window.dataLoader.cacheManager.clearAllLocalCaches()
   ```

### Missing Nov 19 (or Latest) Data

**Debugging steps**:

1. **Check if position files have the data**:
   ```bash
   tail -1 data/agent_data_astock_hour/gemini-2.5-flash-astock-hour/position/position.jsonl | python3 -c "import sys,json; print(json.loads(sys.stdin.read())['date'])"
   # Should show: 2025-11-19 15:00:00 (or latest date)
   ```

2. **Check if price data exists**:
   ```bash
   head -1 docs/data/A_stock/merged_hourly.jsonl | python3 -c "
   import sys, json
   data = json.loads(sys.stdin.read())
   symbol = data['Meta Data']['2. Symbol']
   ts = data['Time Series (60min)']
   nov19_keys = [k for k in ts.keys() if k.startswith('2025-11-19')]
   print(f'{symbol} Nov 19 timestamps: {nov19_keys}')
   "
   ```

3. **Check for N/A prices**:
   ```bash
   # Check if 15:00 has complete data
   head -10 docs/data/A_stock/merged_hourly.jsonl | python3 -c "
   import sys, json
   for line in sys.stdin:
       data = json.loads(line)
       symbol = data['Meta Data']['2. Symbol']
       ts = data['Time Series (60min)']
       if '2025-11-19 15:00:00' in ts:
           price = ts['2025-11-19 15:00:00'].get('4. sell price')
           if not price or price == 'N/A':
               print(f'{symbol} @ 15:00 - MISSING/NA')
   "
   ```

4. **Test price lookup directly**:
   ```python
   # Create test script
   import sys
   sys.path.insert(0, 'scripts')
   from precompute_frontend_cache import load_price_data_cn, get_closing_price
   import yaml

   with open('docs/config.yaml') as f:
       config = yaml.safe_load(f)

   cn_hour_config = config['markets']['cn_hour']
   price_cache = load_price_data_cn(cn_hour_config)

   # Test a specific timestamp
   price = get_closing_price('601318.SH', '2025-11-19 10:30:00', price_cache, 'cn')
   print(f"Price: {price}")  # Should NOT be 0.0 or None
   ```

### Performance Still Slow

1. **Check if caching is enabled**:
   ```bash
   grep 'enabled: true' docs/config.yaml | grep -A5 'cache:'
   ```

2. **Verify cache loading in console**:
   - Open DevTools → Console
   - Look for: `[CacheManager] ✓ Server cache loaded for cn_hour`
   - Should show version and agent count

3. **Check Network tab**:
   - Filter by: `cache.json`
   - Should see cached files (200 OK, ~1-3 MB)
   - If missing, cache files not being served

4. **Test localStorage**:
   ```javascript
   // In browser console
   Object.keys(localStorage).filter(k => k.startsWith('aitrader_'))
   // Should show: ['aitrader_cache_us', 'aitrader_cache_cn', 'aitrader_cache_cn_hour']
   ```

### 1D/1H Toggle Not Working

1. **Check if both caches exist**:
   ```bash
   ls docs/data/cn_cache.json docs/data/cn_hour_cache.json
   # Both should exist
   ```

2. **Check cache generation logs**:
   ```bash
   python3 scripts/precompute_frontend_cache.py 2>&1 | grep -A5 "CN_HOUR"
   # Should show: "Processing gemini-2.5-flash-astock-hour..."
   #              "✓ 121 positions, 120 data points (hourly)"
   ```

3. **Verify market configs**:
   ```bash
   grep -A10 'cn_hour:' docs/config.yaml | grep -E '(time_granularity|price_data_file)'
   # Should show:
   #   time_granularity: "hourly"
   #   price_data_file: "A_stock/merged_hourly.jsonl"
   ```

4. **Check console when toggling**:
   - Click 1H button
   - Console should show: `[CacheManager] Loading server cache for cn_hour market...`
   - If showing "cn" instead, JavaScript toggle not working

### Debugging Price Lookup Issues

If prices are returning 0.0 or None:

1. **Check price_cache keys**:
   ```python
   import sys, yaml
   sys.path.insert(0, 'scripts')
   from precompute_frontend_cache import load_price_data_cn

   with open('docs/config.yaml') as f:
       config = yaml.safe_load(f)

   price_cache = load_price_data_cn(config['markets']['cn_hour'])

   # Check one symbol
   symbol = '601318.SH'
   prices = price_cache[symbol]
   nov19_keys = sorted([k for k in prices.keys() if k.startswith('2025-11-19')])
   print(f"Nov 19 keys: {nov19_keys}")
   # Should show: ['2025-11-19 10:30:00', '2025-11-19 11:30:00', ...]
   # NOT: ['2025-11-19']  ← daily keys would be wrong!
   ```

2. **Verify exact match logic**:
   ```python
   from precompute_frontend_cache import get_closing_price

   # Should use exact match
   date = '2025-11-19 10:30:00'
   price = get_closing_price('601318.SH', date, price_cache, 'cn')
   print(f"Price for {date}: {price}")

   # Should NOT accidentally get 15:00 price (which is None)
   ```

3. **Check for look-ahead errors**:
   ```python
   # This should return 10:30 price, NOT 15:00 price
   price_1030 = get_closing_price('601318.SH', '2025-11-19 10:30:00', price_cache, 'cn')
   price_1500 = get_closing_price('601318.SH', '2025-11-19 15:00:00', price_cache, 'cn')

   print(f"10:30 price: {price_1030}")  # Should be valid
   print(f"15:00 price: {price_1500}")  # May be None (incomplete)

   # If both return the same value, you have a look-ahead bug!
   ```

## GitHub Pages Deployment

### Automatic Deployment via GitHub Actions

The project uses **`.github/workflows/deploy-pages.yml`** to automatically build and deploy with fresh cache files.

**How it works**:
1. Triggered on every push to `main` branch (or manual trigger)
2. Generates cache files during build: `python3 scripts/precompute_frontend_cache.py`
3. Uploads `docs/` folder (including generated caches) to GitHub Pages
4. Deploys to GitHub Pages

**Benefits**:
- ✅ **No bot commits** - Clean git history
- ✅ **Always fresh cache** - Regenerated on every deploy
- ✅ **Smaller repo** - Cache files not tracked in git (6.7 MB saved)
- ✅ **No merge conflicts** - Multiple contributors can work freely

**Setup Required**:

1. **Enable GitHub Actions deployment**:
   - Go to GitHub Settings → **Pages**
   - Under "Build and deployment"
   - Source: Select **"GitHub Actions"** (not "Deploy from a branch")

2. **Verify cache files are ignored**:
   ```bash
   git check-ignore data/*_cache.json
   # Should show: data/us_cache.json, data/cn_cache.json, data/cn_hour_cache.json
   ```

3. **Manual trigger** (if needed):
   - Go to **Actions** tab in GitHub
   - Select **"Deploy GitHub Pages with Cache"**
   - Click **"Run workflow"**

**Important**: Cache files (`*_cache.json`) are in `.gitignore` and should **never be committed**.

### Manual Deployment

Before pushing to GitHub:

```bash
# 1. Regenerate all caches (us, cn, cn_hour)
bash scripts/regenerate_cache.sh

# 2. Verify all three files generated
ls -lh docs/data/*_cache.json

# 3. Commit and push
git add docs/data/us_cache.json docs/data/cn_cache.json docs/data/cn_hour_cache.json
git commit -m "Update frontend cache [skip ci]"
git push
```

**Note**: Cache files are large (~6.7 MB total), ensure Git LFS is configured if needed.

## Development Workflow

### Adding a New Market

To add support for a new market (e.g., crypto):

1. **Add market config** in `docs/config.yaml`:
   ```yaml
   markets:
     crypto:
       name: "Crypto Market"
       time_granularity: "hourly"  # or "daily"
       price_data_type: "merged"   # or "individual"
       price_data_file: "crypto/merged_hourly.jsonl"
       enabled: true
       agents:
         - folder: "agent-crypto"
           display_name: "Agent"
           enabled: true
   ```

2. **Modify `load_price_data_*()` if needed**:
   - For standard formats, existing code should work
   - For custom formats, add market-specific loading logic

3. **Regenerate cache**:
   ```bash
   python3 scripts/precompute_frontend_cache.py
   ```

4. **Test toggle functionality** (if applicable):
   - Ensure JavaScript in `data-loader.js` handles new market ID
   - Test switching between time granularities

### Modifying Price Lookup Logic

When modifying `get_closing_price()`:

1. **Understand current logic**:
   - Exact match → Daily match → Prefix match
   - Must check for N/A values
   - Must never look ahead (use `<=` for timestamp filtering)

2. **Test with edge cases**:
   ```python
   # Test incomplete data (15:00)
   price = get_closing_price(symbol, '2025-11-19 15:00:00', price_cache, 'cn')
   assert price is None or price == 0.0

   # Test complete data (10:30)
   price = get_closing_price(symbol, '2025-11-19 10:30:00', price_cache, 'cn')
   assert price > 0
   ```

3. **Verify no look-ahead**:
   ```python
   # These should return DIFFERENT values
   price_1030 = get_closing_price(symbol, '2025-11-19 10:30:00', price_cache, 'cn')
   price_1500 = get_closing_price(symbol, '2025-11-19 15:00:00', price_cache, 'cn')
   assert price_1030 != price_1500 or price_1500 is None
   ```

4. **Regenerate and test**:
   ```bash
   # Bump version to force browser cache invalidation
   # Edit CACHE_FORMAT_VERSION in precompute_frontend_cache.py
   python3 scripts/precompute_frontend_cache.py
   ```

### Adding Hourly Support to Existing Market

To add hourly granularity to an existing daily market:

1. **Create hourly price data file**:
   ```bash
   # Ensure timestamps include time component
   # Format: "YYYY-MM-DD HH:MM:SS"
   ```

2. **Add `{market}_hour` config** in `docs/config.yaml`:
   ```yaml
   {market}_hour:
     name: "{Market} (Hourly)"
     time_granularity: "hourly"
     price_data_file: "{market}/merged_hourly.jsonl"
     enabled: false  # Hidden, toggled by JS
   ```

3. **Add toggle button** in frontend (HTML):
   ```html
   <button class="granularity-btn" data-granularity="1D">1D</button>
   <button class="granularity-btn" data-granularity="1H">1H</button>
   ```

4. **Add toggle handler** in JavaScript:
   ```javascript
   // Switch between {market} and {market}_hour
   const newMarketId = granularity === '1H' ? `${baseMarket}_hour` : baseMarket;
   ```

5. **Regenerate both caches**:
   ```bash
   python3 scripts/precompute_frontend_cache.py
   # Should generate both {market}_cache.json and {market}_hour_cache.json
   ```

## Benefits

✅ **10-100x faster page loads** (500ms vs 5-10s)
✅ **Multi-market support** (US, CN daily, CN hourly)
✅ **Instant 1D/1H toggle** (no recalculation)
✅ **Works with GitHub Pages** (static hosting)
✅ **Simple and maintainable** (one Python script, one JS module)
✅ **Automatic version detection** (no manual cache invalidation)
✅ **Graceful degradation** (falls back if cache unavailable)
✅ **Browser-side caching** (instant loads after first visit)
✅ **Market-specific caching** (each market cached independently)
✅ **Anti-look-ahead protection** (never returns future prices)

## Key Fixes and Design Decisions

### Browser HTTP Cache Issue (v4 Critical Fix)

**Problem**: After regenerating cache files with new data, browser continued showing old cached values (e.g., SSE-50 at ¥101,529 instead of ¥99,991)

**Root Cause**: The `cache-manager.js` fetch call didn't include cache-busting headers, so browser's HTTP cache served stale `*_cache.json` files without checking the server

**Solution**: Added cache-busting to `loadServerCache()` method:
```javascript
const timestamp = Date.now();
const response = await fetch(`./data/${market}_cache.json?v=${timestamp}`, {
    cache: 'no-store',
    headers: {
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0'
    }
});
```

**Impact**: This ensures version detection works correctly - the browser always fetches the latest cache file from server, compares versions, and updates localStorage when data changes.

### Nov 19, 2025 Data Inclusion Fix

**Problem**: Hourly A-shares cache stopped at Nov 18, missing Nov 19 data

**Root Causes Identified**:
1. `load_price_data_cn()` was loading hourly file but keeping only daily keys
2. `get_closing_price()` was taking last timestamp of day (15:00 with N/A) instead of exact match

**Solutions Implemented**:
1. Made `load_price_data_cn()` dynamic based on `time_granularity`
2. Modified `get_closing_price()` to try exact match first, check for N/A values
3. Added anti-look-ahead protection (only use timestamps ≤ requested time)

### Benchmark Scaling Fix

**Problem**: SSE 50 Index baseline appeared 10x too low (¥10,000 vs ¥100,000 agents)

**Solution**: Modified benchmark processing to extract initial value from first agent's data instead of using hardcoded values

### Multi-Market Architecture

**Design Decision**: Generate caches for ALL markets (even `enabled: false` ones)

**Rationale**:
- Enables 1D/1H toggle to work instantly (both caches pre-generated)
- `cn_hour` has `enabled: false` (hidden from market selector) but cache still generated
- JavaScript can switch between `cn` and `cn_hour` without regeneration

### Version Management

**Design Decision**: Two-part versioning (manual prefix + file hash)

**Rationale**:
- Manual prefix (`v3`, `v4`) for structural changes → forces browser cache invalidation
- File hash auto-updates when trading data changes → auto-invalidation on data updates
- No manual clearing needed for data updates, only for structural changes

## Future Improvements

Potential enhancements for future development:

- [ ] **Incremental updates**: Only recalculate changed agents instead of full regeneration
- [ ] **Compression**: gzip cache files to reduce size (6.7 MB → ~1 MB)
- [ ] **Web Workers**: Parallel cache loading for faster initialization
- [ ] **Service Worker**: Offline caching for PWA support
- [ ] **Cache warming**: Preload inactive markets on idle
- [ ] **Delta updates**: Download only diff from last version
- [ ] **Real-time updates**: WebSocket for live data updates without full regeneration
- [ ] **CDN integration**: Serve cache files from CDN for global performance

## Summary

The AI-Trader frontend caching system provides a comprehensive solution for fast page loads across multiple markets with different time granularities. The two-tier architecture (server pre-computation + browser localStorage) ensures optimal performance while maintaining data integrity through careful version management and anti-look-ahead protections.

**Key achievements**:
- 120 hourly data points for CN market (Oct 9 08:30 → Nov 19 14:00)
- Instant 1D/1H toggle with seamless market switching
- Automatic incomplete data filtering (e.g., Nov 19 15:00 excluded due to N/A prices)
- Multi-market support with market-specific caching strategies
- Robust error handling and graceful degradation

**For maintainers**: Follow the development workflow section when adding new markets or modifying price lookup logic. Always test with edge cases and verify no look-ahead errors are introduced.
