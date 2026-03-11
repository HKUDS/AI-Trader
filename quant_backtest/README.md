# Quant Backtest

**A Free, Zero-Cost Quantitative Algorithm Tracking & Backtesting Platform**

## Features

- **100% Free** - No API keys, subscriptions, or hidden costs
- **Multiple Strategies** - SMA Crossover, RSI, MACD, Bollinger Bands, Momentum, Mean Reversion
- **Rich Analytics** - Sharpe ratio, Sortino ratio, max drawdown, win rate, and more
- **Interactive Charts** - Equity curves, drawdown charts, return distributions
- **Fully Customizable** - Easy to modify parameters and create custom strategies
- **Multiple Data Sources** - Sample data, Yahoo Finance (free), local files

## Quick Start

### Installation

```bash
# Install dependencies
pip install -r quant_backtest/requirements.txt

# Or install individually
pip install streamlit plotly yfinance pandas
```

### Run Web Interface

```bash
# Method 1: Using the launcher
python quant_backtest/run_app.py

# Method 2: Using streamlit directly
streamlit run quant_backtest/ui/app.py
```

Then open http://localhost:8501 in your browser.

### Run from Command Line

```bash
# Basic usage with defaults
python -m quant_backtest.cli

# Custom strategy and symbols
python -m quant_backtest.cli --strategy "RSI" --symbols AAPL MSFT

# Save results to file
python -m quant_backtest.cli --output results.json --cash 50000

# List available strategies
python -m quant_backtest.cli --list-strategies
```

### Use as Python Library

```python
from quant_backtest import BacktestEngine
from quant_backtest.strategies import SMACrossoverStrategy
from quant_backtest.data import generate_sample_data

# Generate sample data (no API needed)
data = generate_sample_data(
    symbols=["AAPL", "GOOGL", "MSFT"],
    start_date="2023-01-01",
    end_date="2024-01-01",
)

# Create backtest engine
engine = BacktestEngine(initial_cash=100000)
engine.load_data(data)

# Set strategy
strategy = SMACrossoverStrategy(
    fast_period=10,
    slow_period=30,
    position_size=20.0,
)
engine.set_strategy(strategy)

# Run backtest
results = engine.run()

# View results
results.metrics.print_summary()
print(f"Total Return: {results.metrics.total_return:.2f}%")
print(f"Sharpe Ratio: {results.metrics.sharpe_ratio:.3f}")
```

## Available Strategies

| Strategy | Description | Key Parameters |
|----------|-------------|----------------|
| **SMA Crossover** | Buy on golden cross, sell on death cross | fast_period, slow_period |
| **RSI** | Buy oversold, sell overbought | rsi_period, oversold, overbought |
| **MACD** | Trade on MACD/signal crossovers | fast_period, slow_period, signal_period |
| **Bollinger Bands** | Mean reversion using volatility bands | period, std_dev |
| **Momentum** | Trade based on price momentum | lookback, buy_threshold, sell_threshold |
| **Mean Reversion** | Buy when price deviates from MA | ma_period, entry_deviation |

## Creating Custom Strategies

```python
from quant_backtest.strategies import BaseStrategy

class MyStrategy(BaseStrategy):
    def __init__(self, threshold: float = 5.0, **kwargs):
        super().__init__(**kwargs)
        self.threshold = threshold

    def on_bar(self, data):
        for symbol in self.symbols:
            prices = self.get_historical_prices(symbol, 20)
            if len(prices) < 20:
                continue

            avg_price = sum(prices) / len(prices)
            current_price = data.get_price(symbol)

            # Buy when price is below average
            if current_price < avg_price * (1 - self.threshold / 100):
                if not self.has_position(symbol):
                    self.buy(symbol, amount=10000)

            # Sell when price is above average
            elif current_price > avg_price * (1 + self.threshold / 100):
                if self.has_position(symbol):
                    self.close_position(symbol)

    def get_parameters(self):
        return {"threshold": self.threshold}
```

## Data Sources

### Sample Data (Instant, No API)
```python
from quant_backtest.data import generate_sample_data

data = generate_sample_data(
    symbols=["AAPL", "GOOGL"],
    start_date="2023-01-01",
    end_date="2024-01-01",
)
```

### Yahoo Finance (Free, No API Key)
```python
from quant_backtest.data import DataFetcher

fetcher = DataFetcher()
data = fetcher.fetch_yahoo(
    symbols=["AAPL", "GOOGL"],
    start_date="2023-01-01",
    end_date="2024-01-01",
)
```

### Local Files
```python
fetcher = DataFetcher()

# JSON file
data = fetcher.load_json("path/to/data.json")

# CSV file
data = fetcher.load_csv("path/to/prices.csv", symbol="AAPL")
```

## Performance Metrics

The platform calculates comprehensive metrics:

**Return Metrics:**
- Total Return
- Annualized Return
- Monthly Returns

**Risk Metrics:**
- Volatility (annualized)
- Max Drawdown
- Value at Risk (VaR)

**Risk-Adjusted Metrics:**
- Sharpe Ratio
- Sortino Ratio
- Calmar Ratio

**Trade Statistics:**
- Total Trades
- Win Rate
- Profit Factor
- Average Trade Return

## Configuration

### Portfolio Settings
```python
from quant_backtest.core import BacktestConfig

config = BacktestConfig(
    initial_cash=100000.0,      # Starting capital
    commission_rate=0.001,       # 0.1% commission
    slippage_rate=0.0005,        # 0.05% slippage
    max_position_size=0.25,      # Max 25% per position
    allow_shorting=False,        # No short selling
)
```

### User Settings
```python
from quant_backtest.config import Settings, save_settings

settings = Settings()
settings.portfolio.initial_cash = 50000
settings.ui.theme = "dark"
save_settings(settings)
```

## Project Structure

```
quant_backtest/
├── core/                  # Core backtesting engine
│   ├── backtest_engine.py # Main engine
│   ├── portfolio.py       # Portfolio management
│   ├── metrics.py         # Performance metrics
│   └── order.py           # Order handling
├── strategies/            # Trading strategies
│   ├── base_strategy.py   # Base class
│   ├── sma_crossover.py   # SMA strategy
│   ├── rsi_strategy.py    # RSI strategy
│   ├── macd_strategy.py   # MACD strategy
│   └── ...
├── data/                  # Data handling
│   ├── data_fetcher.py    # Data fetching
│   └── sample_data.py     # Sample data generator
├── config/                # Configuration
│   └── settings.py        # User settings
├── ui/                    # Web interface
│   └── app.py             # Streamlit app
├── utils/                 # Utilities
│   └── visualization.py   # Charts
├── cli.py                 # Command line interface
├── run_app.py             # App launcher
└── requirements.txt       # Dependencies
```

## License

MIT License - Free to use, modify, and distribute.

## Contributing

Contributions welcome! Feel free to:
- Add new strategies
- Improve metrics calculations
- Enhance visualizations
- Fix bugs

## Support

For issues and questions, please open a GitHub issue.
