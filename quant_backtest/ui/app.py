"""
Streamlit Web Application for Quant Backtest

A free, zero-cost quantitative algorithm tracking and backtesting platform.

Run with: streamlit run quant_backtest/ui/app.py
"""

import streamlit as st
from datetime import datetime, timedelta
from typing import Dict, List, Any
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from quant_backtest.core import BacktestEngine, BacktestConfig
from quant_backtest.strategies import (
    STRATEGY_REGISTRY,
    list_strategies,
    SMACrossoverStrategy,
    RSIStrategy,
    MACDStrategy,
    BollingerBandsStrategy,
    MomentumStrategy,
    MeanReversionStrategy,
)
from quant_backtest.data import DataFetcher, generate_sample_data, SAMPLE_SYMBOLS
from quant_backtest.config import Settings, load_settings, save_settings
from quant_backtest.utils.visualization import (
    plot_equity_curve,
    plot_drawdown,
    plot_returns_distribution,
    plot_monthly_returns,
    create_performance_dashboard,
)


# Page configuration
st.set_page_config(
    page_title="Quant Backtest - Free Algorithmic Trading Platform",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


def init_session_state():
    """Initialize session state variables."""
    if "results" not in st.session_state:
        st.session_state.results = None
    if "data" not in st.session_state:
        st.session_state.data = None
    if "settings" not in st.session_state:
        st.session_state.settings = load_settings()


def render_sidebar():
    """Render the sidebar with configuration options."""
    st.sidebar.title("📈 Quant Backtest")
    st.sidebar.markdown("*Free Algorithmic Trading Platform*")
    st.sidebar.markdown("---")

    # Data Source Selection
    st.sidebar.header("📊 Data Source")
    data_source = st.sidebar.selectbox(
        "Select Data Source",
        ["Sample Data (Instant)", "Yahoo Finance (Free)", "AI-Trader Data", "Upload CSV"],
        help="Choose where to get market data. Sample data requires no API."
    )

    # Symbol Selection
    st.sidebar.header("🎯 Symbols")

    if data_source == "Sample Data (Instant)":
        available_symbols = list(SAMPLE_SYMBOLS.keys())
        selected_symbols = st.sidebar.multiselect(
            "Select Symbols",
            available_symbols,
            default=["AAPL", "GOOGL", "MSFT"],
        )
    elif data_source == "Yahoo Finance (Free)":
        symbols_input = st.sidebar.text_input(
            "Enter Symbols (comma-separated)",
            value="AAPL, GOOGL, MSFT",
            help="Enter stock tickers like AAPL, GOOGL, etc."
        )
        selected_symbols = [s.strip().upper() for s in symbols_input.split(",") if s.strip()]
    elif data_source == "AI-Trader Data":
        fetcher = DataFetcher()
        available_symbols = fetcher.get_available_symbols()
        if available_symbols:
            selected_symbols = st.sidebar.multiselect(
                "Select Symbols",
                available_symbols,
                default=available_symbols[:3] if len(available_symbols) >= 3 else available_symbols,
            )
        else:
            st.sidebar.warning("No AI-Trader data found")
            selected_symbols = []
    else:  # Upload CSV
        selected_symbols = []

    # Date Range
    st.sidebar.header("📅 Date Range")
    col1, col2 = st.sidebar.columns(2)
    with col1:
        start_date = st.date_input(
            "Start Date",
            value=datetime.now() - timedelta(days=365),
        )
    with col2:
        end_date = st.date_input(
            "End Date",
            value=datetime.now(),
        )

    # Strategy Selection
    st.sidebar.header("🧠 Strategy")
    strategy_name = st.sidebar.selectbox(
        "Select Strategy",
        list_strategies(),
        help="Choose a trading strategy to backtest"
    )

    # Strategy Parameters
    st.sidebar.subheader("Strategy Parameters")
    strategy_params = render_strategy_params(strategy_name)

    # Portfolio Settings
    st.sidebar.header("💰 Portfolio Settings")
    initial_cash = st.sidebar.number_input(
        "Initial Capital ($)",
        min_value=1000.0,
        max_value=10000000.0,
        value=100000.0,
        step=10000.0,
    )

    commission_rate = st.sidebar.slider(
        "Commission Rate (%)",
        min_value=0.0,
        max_value=1.0,
        value=0.1,
        step=0.01,
    ) / 100

    slippage_rate = st.sidebar.slider(
        "Slippage Rate (%)",
        min_value=0.0,
        max_value=0.5,
        value=0.05,
        step=0.01,
    ) / 100

    # Run Backtest Button
    st.sidebar.markdown("---")
    run_backtest = st.sidebar.button(
        "🚀 Run Backtest",
        use_container_width=True,
        type="primary",
    )

    return {
        "data_source": data_source,
        "symbols": selected_symbols,
        "start_date": start_date,
        "end_date": end_date,
        "strategy_name": strategy_name,
        "strategy_params": strategy_params,
        "initial_cash": initial_cash,
        "commission_rate": commission_rate,
        "slippage_rate": slippage_rate,
        "run_backtest": run_backtest,
    }


def render_strategy_params(strategy_name: str) -> dict:
    """Render strategy-specific parameter inputs."""
    strategy_class = STRATEGY_REGISTRY.get(strategy_name)
    if not strategy_class:
        return {}

    param_info = strategy_class.get_parameter_info()
    params = {}

    for param_name, info in param_info.items():
        param_type = info.get("type", "float")
        default = info.get("default", 0)
        min_val = info.get("min", 0)
        max_val = info.get("max", 100)
        description = info.get("description", param_name)

        if param_type == "int":
            params[param_name] = st.sidebar.slider(
                description,
                min_value=int(min_val),
                max_value=int(max_val),
                value=int(default),
            )
        elif param_type == "float":
            params[param_name] = st.sidebar.slider(
                description,
                min_value=float(min_val),
                max_value=float(max_val),
                value=float(default),
                step=0.1 if max_val <= 10 else 1.0,
            )
        elif param_type == "bool":
            params[param_name] = st.sidebar.checkbox(
                description,
                value=default,
            )

    return params


def load_data(config: dict) -> Dict[str, List[dict]]:
    """Load market data based on configuration."""
    data_source = config["data_source"]
    symbols = config["symbols"]
    start_date = config["start_date"]
    end_date = config["end_date"]

    if not symbols:
        return {}

    if data_source == "Sample Data (Instant)":
        return generate_sample_data(
            symbols=symbols,
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
            seed=42,  # Reproducible results
        )

    elif data_source == "Yahoo Finance (Free)":
        fetcher = DataFetcher()
        try:
            return fetcher.fetch_yahoo(
                symbols=symbols,
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
            )
        except ImportError:
            st.error("yfinance not installed. Run: pip install yfinance")
            return {}

    elif data_source == "AI-Trader Data":
        fetcher = DataFetcher()
        return fetcher.load_ai_trader_data(symbols=symbols)

    return {}


def create_strategy(config: dict):
    """Create strategy instance from configuration."""
    strategy_name = config["strategy_name"]
    params = config["strategy_params"]
    symbols = config["symbols"]

    strategy_class = STRATEGY_REGISTRY.get(strategy_name)
    if not strategy_class:
        raise ValueError(f"Unknown strategy: {strategy_name}")

    return strategy_class(symbols=symbols, **params)


def run_backtest_with_config(config: dict):
    """Run backtest with given configuration."""
    # Load data
    with st.spinner("Loading market data..."):
        data = load_data(config)

    if not data:
        st.error("No data loaded. Please check your configuration.")
        return None

    st.session_state.data = data

    # Create engine
    engine_config = BacktestConfig(
        initial_cash=config["initial_cash"],
        commission_rate=config["commission_rate"],
        slippage_rate=config["slippage_rate"],
    )
    engine = BacktestEngine(config=engine_config)

    # Load data into engine
    engine.load_data(data)

    # Create strategy
    strategy = create_strategy(config)
    engine.set_strategy(strategy)

    # Run backtest
    with st.spinner("Running backtest..."):
        progress_bar = st.progress(0)

        def update_progress(current, total):
            progress_bar.progress(current / total)

        results = engine.run(
            start_date=datetime.combine(config["start_date"], datetime.min.time()),
            end_date=datetime.combine(config["end_date"], datetime.max.time()),
            progress_callback=update_progress,
        )

        progress_bar.empty()

    return results


def render_results(results):
    """Render backtest results."""
    if results is None:
        return

    # Summary metrics
    st.header("📊 Performance Summary")

    metrics = results.metrics.get_summary()

    # Key metrics in columns
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Total Return",
            f"{metrics['total_return']:.2f}%",
            delta=f"{metrics['total_return']:.2f}%",
        )

    with col2:
        st.metric(
            "Sharpe Ratio",
            f"{metrics['sharpe_ratio']:.3f}",
        )

    with col3:
        st.metric(
            "Max Drawdown",
            f"-{metrics['max_drawdown']:.2f}%",
            delta=f"-{metrics['max_drawdown']:.2f}%",
            delta_color="inverse",
        )

    with col4:
        st.metric(
            "Win Rate",
            f"{metrics['win_rate']:.1f}%",
        )

    # Additional metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Trades", metrics['total_trades'])

    with col2:
        st.metric("Sortino Ratio", f"{metrics['sortino_ratio']:.3f}")

    with col3:
        st.metric("Volatility", f"{metrics['volatility']:.2f}%")

    with col4:
        profit_factor = metrics['profit_factor']
        st.metric(
            "Profit Factor",
            f"{profit_factor:.2f}" if isinstance(profit_factor, float) else profit_factor
        )

    # Charts
    st.header("📈 Charts")

    tab1, tab2, tab3, tab4 = st.tabs([
        "Equity Curve",
        "Drawdown",
        "Returns Distribution",
        "Monthly Returns"
    ])

    with tab1:
        fig = plot_equity_curve(
            results.portfolio.equity_curve,
            initial_value=results.config.initial_cash,
        )
        if fig:
            st.plotly_chart(fig, use_container_width=True)

    with tab2:
        fig = plot_drawdown(results.metrics.drawdown_series)
        if fig:
            st.plotly_chart(fig, use_container_width=True)

    with tab3:
        fig = plot_returns_distribution(results.metrics.daily_returns)
        if fig:
            st.plotly_chart(fig, use_container_width=True)

    with tab4:
        fig = plot_monthly_returns(results.metrics.monthly_returns)
        if fig:
            st.plotly_chart(fig, use_container_width=True)

    # Trade History
    st.header("📋 Trade History")

    trades = results.get_trades()
    if trades:
        # Convert to display format
        display_trades = []
        for t in trades:
            display_trades.append({
                "Date": t.get("timestamp", "")[:10] if t.get("timestamp") else "",
                "Symbol": t.get("symbol", ""),
                "Side": t.get("side", "").upper(),
                "Quantity": f"{t.get('filled_quantity', 0):.2f}",
                "Price": f"${t.get('filled_price', 0):.2f}",
                "Commission": f"${t.get('commission', 0):.2f}",
                "Status": t.get("status", ""),
            })

        st.dataframe(display_trades, use_container_width=True)
    else:
        st.info("No trades executed during backtest period.")

    # Download Results
    st.header("💾 Export Results")

    col1, col2 = st.columns(2)

    with col1:
        results_json = json.dumps(results.get_summary(), indent=2, default=str)
        st.download_button(
            "📥 Download Results (JSON)",
            data=results_json,
            file_name="backtest_results.json",
            mime="application/json",
        )

    with col2:
        trades_json = json.dumps(trades, indent=2, default=str)
        st.download_button(
            "📥 Download Trades (JSON)",
            data=trades_json,
            file_name="trade_history.json",
            mime="application/json",
        )


def render_main_content():
    """Render main content area."""
    st.title("🚀 Quant Backtest Platform")
    st.markdown("""
    **Free, open-source quantitative algorithm tracking and backtesting.**

    - ✅ **Zero Cost** - No API keys or subscriptions required
    - 📊 **Multiple Strategies** - SMA, RSI, MACD, Bollinger Bands, and more
    - 📈 **Rich Analytics** - Sharpe ratio, max drawdown, win rate, and more
    - 🔧 **Fully Customizable** - Adjust parameters to match your requirements
    """)

    st.markdown("---")

    # Show results if available
    if st.session_state.results:
        render_results(st.session_state.results)
    else:
        # Show getting started guide
        st.info("👈 Configure your backtest in the sidebar and click **Run Backtest** to begin.")

        st.header("📚 Getting Started")

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Available Strategies")
            for name in list_strategies():
                st.markdown(f"- **{name}**")

        with col2:
            st.subheader("Quick Tips")
            st.markdown("""
            1. **Start Simple** - Use sample data first
            2. **Test Parameters** - Try different strategy settings
            3. **Compare Results** - Run multiple backtests
            4. **Export Data** - Download results for analysis
            """)

        # Sample results preview
        st.subheader("🔮 Sample Preview")
        if st.button("Generate Sample Backtest"):
            sample_config = {
                "data_source": "Sample Data (Instant)",
                "symbols": ["AAPL", "GOOGL", "MSFT"],
                "start_date": datetime.now().date() - timedelta(days=180),
                "end_date": datetime.now().date(),
                "strategy_name": "SMA Crossover",
                "strategy_params": {"fast_period": 10, "slow_period": 30, "position_size": 20.0},
                "initial_cash": 100000.0,
                "commission_rate": 0.001,
                "slippage_rate": 0.0005,
            }
            results = run_backtest_with_config(sample_config)
            if results:
                st.session_state.results = results
                st.rerun()


def main():
    """Main application entry point."""
    init_session_state()

    # Render sidebar and get configuration
    config = render_sidebar()

    # Run backtest if button clicked
    if config["run_backtest"]:
        if not config["symbols"]:
            st.error("Please select at least one symbol.")
        else:
            results = run_backtest_with_config(config)
            if results:
                st.session_state.results = results
                st.rerun()

    # Render main content
    render_main_content()


if __name__ == "__main__":
    main()
