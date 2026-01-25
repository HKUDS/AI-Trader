"""
Visualization utilities for backtesting results.

Uses Plotly for interactive charts (free, no API key needed).
"""

from typing import List, Dict, Tuple, Optional, Any
from datetime import datetime


def plot_equity_curve(
    equity_curve: List[Tuple[datetime, float]],
    title: str = "Portfolio Equity Curve",
    initial_value: Optional[float] = None,
) -> Any:
    """
    Plot the equity curve.

    Args:
        equity_curve: List of (timestamp, equity) tuples
        title: Chart title
        initial_value: Initial portfolio value for baseline

    Returns:
        Plotly figure object
    """
    try:
        import plotly.graph_objects as go
    except ImportError:
        print("Plotly not installed. Install with: pip install plotly")
        return None

    dates = [ts for ts, _ in equity_curve]
    values = [eq for _, eq in equity_curve]

    fig = go.Figure()

    # Equity line
    fig.add_trace(go.Scatter(
        x=dates,
        y=values,
        mode='lines',
        name='Portfolio Value',
        line=dict(color='#2E86AB', width=2),
        fill='tozeroy',
        fillcolor='rgba(46, 134, 171, 0.1)',
    ))

    # Initial value baseline
    if initial_value:
        fig.add_hline(
            y=initial_value,
            line_dash="dash",
            line_color="gray",
            annotation_text=f"Initial: ${initial_value:,.0f}",
        )

    fig.update_layout(
        title=title,
        xaxis_title="Date",
        yaxis_title="Portfolio Value ($)",
        template="plotly_dark",
        hovermode='x unified',
        showlegend=True,
    )

    return fig


def plot_drawdown(
    drawdown_series: List[Tuple[datetime, float]],
    title: str = "Portfolio Drawdown",
) -> Any:
    """
    Plot the drawdown over time.

    Args:
        drawdown_series: List of (timestamp, drawdown%) tuples
        title: Chart title

    Returns:
        Plotly figure object
    """
    try:
        import plotly.graph_objects as go
    except ImportError:
        return None

    dates = [ts for ts, _ in drawdown_series]
    drawdowns = [-dd for _, dd in drawdown_series]  # Negative for visual

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=dates,
        y=drawdowns,
        mode='lines',
        name='Drawdown',
        line=dict(color='#E74C3C', width=1),
        fill='tozeroy',
        fillcolor='rgba(231, 76, 60, 0.3)',
    ))

    fig.update_layout(
        title=title,
        xaxis_title="Date",
        yaxis_title="Drawdown (%)",
        template="plotly_dark",
        hovermode='x unified',
    )

    return fig


def plot_returns_distribution(
    returns: List[float],
    title: str = "Daily Returns Distribution",
    bins: int = 50,
) -> Any:
    """
    Plot histogram of returns.

    Args:
        returns: List of daily returns
        title: Chart title
        bins: Number of histogram bins

    Returns:
        Plotly figure object
    """
    try:
        import plotly.graph_objects as go
    except ImportError:
        return None

    # Convert to percentages
    returns_pct = [r * 100 for r in returns]

    fig = go.Figure()

    fig.add_trace(go.Histogram(
        x=returns_pct,
        nbinsx=bins,
        name='Returns',
        marker_color='#3498DB',
        opacity=0.7,
    ))

    # Add mean line
    mean_return = sum(returns_pct) / len(returns_pct) if returns_pct else 0
    fig.add_vline(
        x=mean_return,
        line_dash="dash",
        line_color="yellow",
        annotation_text=f"Mean: {mean_return:.2f}%",
    )

    fig.update_layout(
        title=title,
        xaxis_title="Daily Return (%)",
        yaxis_title="Frequency",
        template="plotly_dark",
        bargap=0.1,
    )

    return fig


def plot_monthly_returns(
    monthly_returns: Dict[str, float],
    title: str = "Monthly Returns Heatmap",
) -> Any:
    """
    Plot monthly returns as a heatmap.

    Args:
        monthly_returns: Dictionary of "YYYY-MM" -> return%
        title: Chart title

    Returns:
        Plotly figure object
    """
    try:
        import plotly.graph_objects as go
    except ImportError:
        return None

    if not monthly_returns:
        return None

    # Parse months and organize by year
    years = {}
    for month_str, ret in monthly_returns.items():
        year, month = month_str.split("-")
        if year not in years:
            years[year] = [None] * 12
        years[year][int(month) - 1] = ret

    # Create heatmap data
    z_data = list(years.values())
    y_labels = list(years.keys())
    x_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    fig = go.Figure(data=go.Heatmap(
        z=z_data,
        x=x_labels,
        y=y_labels,
        colorscale=[
            [0, '#E74C3C'],    # Red for negative
            [0.5, '#F4F4F4'],  # White for zero
            [1, '#27AE60'],    # Green for positive
        ],
        zmid=0,
        text=[[f"{v:.1f}%" if v is not None else "" for v in row] for row in z_data],
        texttemplate="%{text}",
        textfont={"size": 10},
        hovertemplate="Month: %{x}<br>Year: %{y}<br>Return: %{z:.2f}%<extra></extra>",
    ))

    fig.update_layout(
        title=title,
        template="plotly_dark",
    )

    return fig


def plot_trades(
    trades: List[dict],
    prices: Dict[str, List[dict]],
    symbol: str,
    title: Optional[str] = None,
) -> Any:
    """
    Plot price chart with trade markers.

    Args:
        trades: List of trade dictionaries
        prices: Price data dictionary
        symbol: Symbol to plot
        title: Chart title

    Returns:
        Plotly figure object
    """
    try:
        import plotly.graph_objects as go
    except ImportError:
        return None

    if symbol not in prices:
        return None

    symbol_data = prices[symbol]
    dates = [d["date"] for d in symbol_data]
    closes = [d["close"] for d in symbol_data]

    fig = go.Figure()

    # Price line
    fig.add_trace(go.Scatter(
        x=dates,
        y=closes,
        mode='lines',
        name='Price',
        line=dict(color='#3498DB', width=1),
    ))

    # Buy markers
    buy_trades = [t for t in trades if t.get("symbol") == symbol and t.get("side") == "buy"]
    if buy_trades:
        buy_dates = [t.get("timestamp", "")[:10] for t in buy_trades]
        buy_prices = [t.get("filled_price", 0) for t in buy_trades]
        fig.add_trace(go.Scatter(
            x=buy_dates,
            y=buy_prices,
            mode='markers',
            name='Buy',
            marker=dict(color='#27AE60', size=10, symbol='triangle-up'),
        ))

    # Sell markers
    sell_trades = [t for t in trades if t.get("symbol") == symbol and t.get("side") == "sell"]
    if sell_trades:
        sell_dates = [t.get("timestamp", "")[:10] for t in sell_trades]
        sell_prices = [t.get("filled_price", 0) for t in sell_trades]
        fig.add_trace(go.Scatter(
            x=sell_dates,
            y=sell_prices,
            mode='markers',
            name='Sell',
            marker=dict(color='#E74C3C', size=10, symbol='triangle-down'),
        ))

    fig.update_layout(
        title=title or f"{symbol} - Price with Trades",
        xaxis_title="Date",
        yaxis_title="Price ($)",
        template="plotly_dark",
        hovermode='x unified',
    )

    return fig


def create_performance_dashboard(
    results: Any,  # BacktestResults
    show_trades: bool = True,
) -> Any:
    """
    Create a comprehensive performance dashboard.

    Args:
        results: BacktestResults object
        show_trades: Whether to include trade charts

    Returns:
        Plotly figure with subplots
    """
    try:
        from plotly.subplots import make_subplots
        import plotly.graph_objects as go
    except ImportError:
        return None

    # Create subplot grid
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=(
            "Equity Curve",
            "Drawdown",
            "Returns Distribution",
            "Monthly Returns",
        ),
        specs=[
            [{"type": "scatter"}, {"type": "scatter"}],
            [{"type": "histogram"}, {"type": "heatmap"}],
        ],
        vertical_spacing=0.12,
        horizontal_spacing=0.08,
    )

    # 1. Equity Curve
    equity_data = results.portfolio.equity_curve
    dates = [ts for ts, _ in equity_data]
    values = [eq for _, eq in equity_data]

    fig.add_trace(
        go.Scatter(x=dates, y=values, mode='lines', name='Portfolio',
                   line=dict(color='#2E86AB')),
        row=1, col=1
    )

    # 2. Drawdown
    drawdown_data = results.metrics.drawdown_series
    dd_dates = [ts for ts, _ in drawdown_data]
    dd_values = [-dd for _, dd in drawdown_data]

    fig.add_trace(
        go.Scatter(x=dd_dates, y=dd_values, mode='lines', name='Drawdown',
                   line=dict(color='#E74C3C'), fill='tozeroy'),
        row=1, col=2
    )

    # 3. Returns Distribution
    returns_pct = [r * 100 for r in results.metrics.daily_returns]
    fig.add_trace(
        go.Histogram(x=returns_pct, nbinsx=30, name='Daily Returns',
                     marker_color='#3498DB'),
        row=2, col=1
    )

    # 4. Monthly Returns (simplified bar chart instead of heatmap for subplots)
    monthly = results.metrics.monthly_returns
    months = list(monthly.keys())
    returns = list(monthly.values())
    colors = ['#27AE60' if r >= 0 else '#E74C3C' for r in returns]

    fig.add_trace(
        go.Bar(x=months, y=returns, name='Monthly', marker_color=colors),
        row=2, col=2
    )

    # Update layout
    fig.update_layout(
        height=700,
        template="plotly_dark",
        showlegend=False,
        title_text="Backtest Performance Dashboard",
    )

    return fig


def format_currency(value: float, symbol: str = "$") -> str:
    """Format a value as currency."""
    return f"{symbol}{value:,.2f}"


def format_percent(value: float) -> str:
    """Format a value as percentage."""
    return f"{value:.2f}%"


def format_ratio(value: float) -> str:
    """Format a value as a ratio."""
    return f"{value:.3f}"
