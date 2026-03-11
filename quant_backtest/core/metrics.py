"""
Performance metrics calculation module.

This module provides comprehensive performance analytics including:
- Return metrics (total, annual, monthly)
- Risk metrics (volatility, max drawdown, VaR)
- Risk-adjusted metrics (Sharpe, Sortino, Calmar)
- Trade statistics (win rate, profit factor, etc.)
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Tuple, Optional, Dict
import math
from collections import defaultdict


@dataclass
class PerformanceMetrics:
    """
    Calculate and store performance metrics for a trading strategy.

    Attributes:
        equity_curve: List of (timestamp, equity) tuples
        trades: List of trade dictionaries
        risk_free_rate: Annual risk-free rate for Sharpe calculation
        trading_days_per_year: Number of trading days for annualization
    """
    equity_curve: List[Tuple[datetime, float]]
    trades: List[dict] = None
    risk_free_rate: float = 0.02  # 2% default risk-free rate
    trading_days_per_year: int = 252

    def __post_init__(self):
        if self.trades is None:
            self.trades = []
        self._calculate_returns()

    def _calculate_returns(self) -> None:
        """Calculate daily returns from equity curve."""
        self.daily_returns = []
        self.timestamps = []

        if len(self.equity_curve) < 2:
            return

        for i in range(1, len(self.equity_curve)):
            prev_ts, prev_eq = self.equity_curve[i - 1]
            curr_ts, curr_eq = self.equity_curve[i]

            if prev_eq > 0:
                daily_return = (curr_eq - prev_eq) / prev_eq
                self.daily_returns.append(daily_return)
                self.timestamps.append(curr_ts)

    # ==================== Return Metrics ====================

    @property
    def total_return(self) -> float:
        """Calculate total return percentage."""
        if len(self.equity_curve) < 2:
            return 0.0
        initial = self.equity_curve[0][1]
        final = self.equity_curve[-1][1]
        if initial == 0:
            return 0.0
        return ((final - initial) / initial) * 100

    @property
    def annualized_return(self) -> float:
        """Calculate annualized return percentage."""
        if len(self.equity_curve) < 2:
            return 0.0

        initial = self.equity_curve[0][1]
        final = self.equity_curve[-1][1]
        start_date = self.equity_curve[0][0]
        end_date = self.equity_curve[-1][0]

        days = (end_date - start_date).days
        if days <= 0 or initial <= 0:
            return 0.0

        years = days / 365.25
        if years <= 0:
            return self.total_return

        total_return_decimal = (final - initial) / initial
        annualized = ((1 + total_return_decimal) ** (1 / years)) - 1
        return annualized * 100

    @property
    def monthly_returns(self) -> Dict[str, float]:
        """Calculate returns by month."""
        if len(self.equity_curve) < 2:
            return {}

        monthly = defaultdict(lambda: {"start": None, "end": None})

        for ts, eq in self.equity_curve:
            month_key = ts.strftime("%Y-%m")
            if monthly[month_key]["start"] is None:
                monthly[month_key]["start"] = eq
            monthly[month_key]["end"] = eq

        returns = {}
        for month, values in monthly.items():
            if values["start"] and values["end"] and values["start"] > 0:
                ret = ((values["end"] - values["start"]) / values["start"]) * 100
                returns[month] = round(ret, 2)

        return dict(sorted(returns.items()))

    # ==================== Risk Metrics ====================

    @property
    def volatility(self) -> float:
        """Calculate annualized volatility (standard deviation of returns)."""
        if len(self.daily_returns) < 2:
            return 0.0

        mean = sum(self.daily_returns) / len(self.daily_returns)
        variance = sum((r - mean) ** 2 for r in self.daily_returns) / (len(self.daily_returns) - 1)
        daily_vol = math.sqrt(variance)

        # Annualize
        return daily_vol * math.sqrt(self.trading_days_per_year) * 100

    @property
    def downside_volatility(self) -> float:
        """Calculate downside volatility (only negative returns)."""
        negative_returns = [r for r in self.daily_returns if r < 0]
        if len(negative_returns) < 2:
            return 0.0

        mean = sum(negative_returns) / len(negative_returns)
        variance = sum((r - mean) ** 2 for r in negative_returns) / (len(negative_returns) - 1)
        daily_downside_vol = math.sqrt(variance)

        return daily_downside_vol * math.sqrt(self.trading_days_per_year) * 100

    @property
    def max_drawdown(self) -> float:
        """Calculate maximum drawdown percentage."""
        if len(self.equity_curve) < 2:
            return 0.0

        peak = self.equity_curve[0][1]
        max_dd = 0.0

        for _, equity in self.equity_curve:
            if equity > peak:
                peak = equity
            drawdown = (peak - equity) / peak if peak > 0 else 0
            max_dd = max(max_dd, drawdown)

        return max_dd * 100

    @property
    def drawdown_series(self) -> List[Tuple[datetime, float]]:
        """Calculate drawdown at each point in time."""
        if len(self.equity_curve) < 2:
            return []

        peak = self.equity_curve[0][1]
        drawdowns = []

        for ts, equity in self.equity_curve:
            if equity > peak:
                peak = equity
            dd = ((peak - equity) / peak * 100) if peak > 0 else 0
            drawdowns.append((ts, dd))

        return drawdowns

    @property
    def var_95(self) -> float:
        """Calculate 95% Value at Risk (historical method)."""
        if len(self.daily_returns) < 20:
            return 0.0

        sorted_returns = sorted(self.daily_returns)
        index = int(len(sorted_returns) * 0.05)
        return sorted_returns[index] * 100

    @property
    def var_99(self) -> float:
        """Calculate 99% Value at Risk (historical method)."""
        if len(self.daily_returns) < 100:
            return 0.0

        sorted_returns = sorted(self.daily_returns)
        index = int(len(sorted_returns) * 0.01)
        return sorted_returns[index] * 100

    # ==================== Risk-Adjusted Metrics ====================

    @property
    def sharpe_ratio(self) -> float:
        """
        Calculate Sharpe Ratio.

        Sharpe = (Return - Risk Free Rate) / Volatility
        """
        if self.volatility == 0:
            return 0.0

        excess_return = self.annualized_return - (self.risk_free_rate * 100)
        return excess_return / self.volatility

    @property
    def sortino_ratio(self) -> float:
        """
        Calculate Sortino Ratio.

        Sortino = (Return - Risk Free Rate) / Downside Volatility
        """
        if self.downside_volatility == 0:
            return 0.0

        excess_return = self.annualized_return - (self.risk_free_rate * 100)
        return excess_return / self.downside_volatility

    @property
    def calmar_ratio(self) -> float:
        """
        Calculate Calmar Ratio.

        Calmar = Annualized Return / Max Drawdown
        """
        if self.max_drawdown == 0:
            return 0.0

        return self.annualized_return / self.max_drawdown

    @property
    def information_ratio(self) -> float:
        """Calculate Information Ratio (using 0 as benchmark)."""
        if len(self.daily_returns) < 2:
            return 0.0

        mean_return = sum(self.daily_returns) / len(self.daily_returns)
        tracking_error = math.sqrt(
            sum((r - mean_return) ** 2 for r in self.daily_returns) / len(self.daily_returns)
        )

        if tracking_error == 0:
            return 0.0

        return (mean_return * self.trading_days_per_year) / (tracking_error * math.sqrt(self.trading_days_per_year))

    # ==================== Trade Statistics ====================

    @property
    def total_trades(self) -> int:
        """Get total number of trades."""
        return len(self.trades)

    @property
    def winning_trades(self) -> int:
        """Count winning trades."""
        return sum(1 for t in self.trades
                   if t.get("side") == "sell" and
                   t.get("filled_price", 0) > t.get("avg_cost", float('inf')))

    @property
    def losing_trades(self) -> int:
        """Count losing trades."""
        sells = [t for t in self.trades if t.get("side") == "sell"]
        return len(sells) - self.winning_trades

    @property
    def win_rate(self) -> float:
        """Calculate win rate percentage."""
        sells = [t for t in self.trades if t.get("side") == "sell"]
        if not sells:
            return 0.0
        return (self.winning_trades / len(sells)) * 100

    @property
    def profit_factor(self) -> float:
        """
        Calculate profit factor.

        Profit Factor = Gross Profit / Gross Loss
        """
        gross_profit = 0.0
        gross_loss = 0.0

        for trade in self.trades:
            if trade.get("side") == "sell":
                pnl = (trade.get("filled_price", 0) - trade.get("avg_cost", 0)) * trade.get("filled_quantity", 0)
                if pnl > 0:
                    gross_profit += pnl
                else:
                    gross_loss += abs(pnl)

        if gross_loss == 0:
            return float('inf') if gross_profit > 0 else 0.0

        return gross_profit / gross_loss

    @property
    def avg_trade_return(self) -> float:
        """Calculate average return per trade."""
        if not self.trades:
            return 0.0

        total_return = sum(
            ((t.get("filled_price", 0) - t.get("avg_cost", 0)) / t.get("avg_cost", 1)) * 100
            for t in self.trades if t.get("side") == "sell" and t.get("avg_cost", 0) > 0
        )

        sells = [t for t in self.trades if t.get("side") == "sell"]
        if not sells:
            return 0.0

        return total_return / len(sells)

    @property
    def avg_holding_period(self) -> float:
        """Calculate average holding period in days."""
        # This would require tracking entry/exit times per position
        # Simplified version based on trade frequency
        if len(self.equity_curve) < 2 or self.total_trades == 0:
            return 0.0

        total_days = (self.equity_curve[-1][0] - self.equity_curve[0][0]).days
        return total_days / max(self.total_trades // 2, 1)

    @property
    def total_commission(self) -> float:
        """Calculate total commission paid."""
        return sum(t.get("commission", 0) for t in self.trades)

    # ==================== Summary Methods ====================

    def get_summary(self) -> dict:
        """Get comprehensive performance summary."""
        return {
            # Return metrics
            "total_return": round(self.total_return, 2),
            "annualized_return": round(self.annualized_return, 2),

            # Risk metrics
            "volatility": round(self.volatility, 2),
            "max_drawdown": round(self.max_drawdown, 2),
            "var_95": round(self.var_95, 2),

            # Risk-adjusted metrics
            "sharpe_ratio": round(self.sharpe_ratio, 3),
            "sortino_ratio": round(self.sortino_ratio, 3),
            "calmar_ratio": round(self.calmar_ratio, 3),

            # Trade statistics
            "total_trades": self.total_trades,
            "win_rate": round(self.win_rate, 2),
            "profit_factor": round(self.profit_factor, 3) if self.profit_factor != float('inf') else "Inf",
            "avg_trade_return": round(self.avg_trade_return, 2),
            "total_commission": round(self.total_commission, 2),

            # Period info
            "start_date": self.equity_curve[0][0].strftime("%Y-%m-%d") if self.equity_curve else None,
            "end_date": self.equity_curve[-1][0].strftime("%Y-%m-%d") if self.equity_curve else None,
            "trading_days": len(self.equity_curve),
        }

    def get_monthly_summary(self) -> List[dict]:
        """Get monthly performance breakdown."""
        monthly = self.monthly_returns
        return [{"month": m, "return": r} for m, r in monthly.items()]

    def print_summary(self) -> None:
        """Print formatted performance summary."""
        summary = self.get_summary()

        print("\n" + "=" * 60)
        print("PERFORMANCE SUMMARY")
        print("=" * 60)

        print(f"\n{'RETURNS':^60}")
        print("-" * 60)
        print(f"  Total Return:        {summary['total_return']:>10.2f}%")
        print(f"  Annualized Return:   {summary['annualized_return']:>10.2f}%")

        print(f"\n{'RISK METRICS':^60}")
        print("-" * 60)
        print(f"  Volatility:          {summary['volatility']:>10.2f}%")
        print(f"  Max Drawdown:        {summary['max_drawdown']:>10.2f}%")
        print(f"  VaR (95%):           {summary['var_95']:>10.2f}%")

        print(f"\n{'RISK-ADJUSTED METRICS':^60}")
        print("-" * 60)
        print(f"  Sharpe Ratio:        {summary['sharpe_ratio']:>10.3f}")
        print(f"  Sortino Ratio:       {summary['sortino_ratio']:>10.3f}")
        print(f"  Calmar Ratio:        {summary['calmar_ratio']:>10.3f}")

        print(f"\n{'TRADE STATISTICS':^60}")
        print("-" * 60)
        print(f"  Total Trades:        {summary['total_trades']:>10}")
        print(f"  Win Rate:            {summary['win_rate']:>10.2f}%")
        print(f"  Profit Factor:       {str(summary['profit_factor']):>10}")
        print(f"  Avg Trade Return:    {summary['avg_trade_return']:>10.2f}%")
        print(f"  Total Commission:    ${summary['total_commission']:>9.2f}")

        print(f"\n{'PERIOD':^60}")
        print("-" * 60)
        print(f"  Start Date:          {summary['start_date'] or 'N/A':>10}")
        print(f"  End Date:            {summary['end_date'] or 'N/A':>10}")
        print(f"  Trading Days:        {summary['trading_days']:>10}")

        print("\n" + "=" * 60)

    def __repr__(self) -> str:
        return (f"PerformanceMetrics(return={self.total_return:.2f}%, "
                f"sharpe={self.sharpe_ratio:.3f}, "
                f"max_dd={self.max_drawdown:.2f}%)")
