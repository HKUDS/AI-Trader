"""
Real-time API Cost Tracking

Track and monitor AI API costs across providers
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict


@dataclass
class CostRecord:
    """Single cost record"""
    timestamp: str
    provider: str
    model: str
    tokens_input: int
    tokens_output: int
    cost_usd: float
    endpoint: str
    success: bool


class CostTracker:
    """
    Track API costs in real-time
    
    Features:
    - Per-provider cost tracking
    - Daily/monthly summaries
    - Budget alerts
    - Export to JSON/CSV
    """
    
    # Pricing per 1K tokens (as of 2025-01-06)
    PRICING = {
        "github_models": {
            "gpt-4o": {"input": 0.0, "output": 0.0},  # Free!
            "gpt-4o-mini": {"input": 0.0, "output": 0.0},  # Free!
            "claude-3.5-sonnet": {"input": 0.0, "output": 0.0},  # Free!
        },
        "anthropic": {
            "claude-3.7-sonnet": {"input": 0.003, "output": 0.015},
            "claude-3.5-sonnet": {"input": 0.003, "output": 0.015},
            "claude-3-opus": {"input": 0.015, "output": 0.075},
        },
        "openai": {
            "gpt-4o": {"input": 0.0025, "output": 0.010},
            "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
            "gpt-4-turbo": {"input": 0.010, "output": 0.030},
        }
    }
    
    def __init__(self, log_file: str = "./data/cost_tracking.jsonl"):
        """
        Initialize cost tracker
        
        Args:
            log_file: Path to cost log file
        """
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Budget limits (USD)
        self.daily_budget = float('inf')
        self.monthly_budget = float('inf')
        
        # Alert thresholds
        self.alert_threshold = 0.8  # Alert at 80% of budget
        
        print(f"✅ Cost tracker initialized: {self.log_file}")
    
    def set_budgets(self, daily: Optional[float] = None, monthly: Optional[float] = None):
        """Set budget limits"""
        if daily:
            self.daily_budget = daily
            print(f"💰 Daily budget set: ${daily:.2f}")
        
        if monthly:
            self.monthly_budget = monthly
            print(f"💰 Monthly budget set: ${monthly:.2f}")
    
    def calculate_cost(
        self,
        provider: str,
        model: str,
        tokens_input: int,
        tokens_output: int
    ) -> float:
        """
        Calculate cost for API call
        
        Args:
            provider: Provider name (github_models, anthropic, openai)
            model: Model name
            tokens_input: Input tokens
            tokens_output: Output tokens
            
        Returns:
            Cost in USD
        """
        pricing = self.PRICING.get(provider, {}).get(model, {"input": 0, "output": 0})
        
        cost_input = (tokens_input / 1000) * pricing["input"]
        cost_output = (tokens_output / 1000) * pricing["output"]
        
        return cost_input + cost_output
    
    def record(
        self,
        provider: str,
        model: str,
        tokens_input: int,
        tokens_output: int,
        endpoint: str = "completion",
        success: bool = True
    ) -> float:
        """
        Record an API call
        
        Args:
            provider: Provider name
            model: Model name
            tokens_input: Input tokens
            tokens_output: Output tokens
            endpoint: API endpoint called
            success: Whether call was successful
            
        Returns:
            Cost in USD
        """
        cost = self.calculate_cost(provider, model, tokens_input, tokens_output)
        
        record = CostRecord(
            timestamp=datetime.now().isoformat(),
            provider=provider,
            model=model,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            cost_usd=cost,
            endpoint=endpoint,
            success=success
        )
        
        # Append to log file
        with open(self.log_file, 'a') as f:
            json.dump(asdict(record), f)
            f.write('\n')
        
        # Check budgets
        self._check_budgets()
        
        return cost
    
    def _check_budgets(self):
        """Check if budgets are exceeded"""
        today_cost = self.get_daily_cost()
        month_cost = self.get_monthly_cost()
        
        # Daily budget check
        if today_cost >= self.daily_budget * self.alert_threshold:
            print(f"⚠️ BUDGET ALERT: Daily spending at ${today_cost:.2f} / ${self.daily_budget:.2f}")
        
        if today_cost >= self.daily_budget:
            print(f"🚨 BUDGET EXCEEDED: Daily limit of ${self.daily_budget:.2f} reached!")
        
        # Monthly budget check
        if month_cost >= self.monthly_budget * self.alert_threshold:
            print(f"⚠️ BUDGET ALERT: Monthly spending at ${month_cost:.2f} / ${self.monthly_budget:.2f}")
        
        if month_cost >= self.monthly_budget:
            print(f"🚨 BUDGET EXCEEDED: Monthly limit of ${self.monthly_budget:.2f} reached!")
    
    def get_daily_cost(self, date: Optional[str] = None) -> float:
        """Get total cost for a specific day"""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        return self._get_cost_for_period(date)
    
    def get_monthly_cost(self, month: Optional[str] = None) -> float:
        """Get total cost for a specific month"""
        if month is None:
            month = datetime.now().strftime("%Y-%m")
        
        return self._get_cost_for_period(month)
    
    def _get_cost_for_period(self, period: str) -> float:
        """Get cost for a time period (prefix match)"""
        if not self.log_file.exists():
            return 0.0
        
        total = 0.0
        with open(self.log_file, 'r') as f:
            for line in f:
                record = json.loads(line)
                if record['timestamp'].startswith(period) and record['success']:
                    total += record['cost_usd']
        
        return total
    
    def get_stats(self) -> Dict[str, any]:
        """Get comprehensive cost statistics"""
        if not self.log_file.exists():
            return {}
        
        stats = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "total_cost": 0.0,
            "total_tokens_input": 0,
            "total_tokens_output": 0,
            "by_provider": {},
            "by_model": {},
            "daily_cost": self.get_daily_cost(),
            "monthly_cost": self.get_monthly_cost()
        }
        
        with open(self.log_file, 'r') as f:
            for line in f:
                record = json.loads(line)
                
                stats["total_calls"] += 1
                
                if record['success']:
                    stats["successful_calls"] += 1
                    stats["total_cost"] += record['cost_usd']
                    stats["total_tokens_input"] += record['tokens_input']
                    stats["total_tokens_output"] += record['tokens_output']
                    
                    # By provider
                    provider = record['provider']
                    if provider not in stats["by_provider"]:
                        stats["by_provider"][provider] = {"calls": 0, "cost": 0.0}
                    stats["by_provider"][provider]["calls"] += 1
                    stats["by_provider"][provider]["cost"] += record['cost_usd']
                    
                    # By model
                    model = record['model']
                    if model not in stats["by_model"]:
                        stats["by_model"][model] = {"calls": 0, "cost": 0.0}
                    stats["by_model"][model]["calls"] += 1
                    stats["by_model"][model]["cost"] += record['cost_usd']
                else:
                    stats["failed_calls"] += 1
        
        return stats
    
    def print_summary(self):
        """Print cost summary"""
        stats = self.get_stats()
        
        if not stats:
            print("No cost data available yet.")
            return
        
        print("\n" + "=" * 60)
        print("💰 API COST SUMMARY")
        print("=" * 60)
        
        print(f"\n📊 Overall:")
        print(f"   Total calls: {stats['total_calls']}")
        print(f"   Successful: {stats['successful_calls']}")
        print(f"   Failed: {stats['failed_calls']}")
        print(f"   Success rate: {(stats['successful_calls'] / stats['total_calls'] * 100):.1f}%")
        
        print(f"\n💵 Costs:")
        print(f"   Today: ${stats['daily_cost']:.4f}")
        print(f"   This month: ${stats['monthly_cost']:.4f}")
        print(f"   All time: ${stats['total_cost']:.4f}")
        
        print(f"\n🔢 Tokens:")
        print(f"   Input: {stats['total_tokens_input']:,}")
        print(f"   Output: {stats['total_tokens_output']:,}")
        print(f"   Total: {stats['total_tokens_input'] + stats['total_tokens_output']:,}")
        
        print(f"\n🤖 By Provider:")
        for provider, data in stats["by_provider"].items():
            print(f"   {provider}: {data['calls']} calls, ${data['cost']:.4f}")
        
        print(f"\n📱 By Model:")
        for model, data in stats["by_model"].items():
            print(f"   {model}: {data['calls']} calls, ${data['cost']:.4f}")
        
        # Budget status
        if self.daily_budget < float('inf'):
            daily_pct = (stats['daily_cost'] / self.daily_budget * 100)
            print(f"\n📈 Budget Status:")
            print(f"   Daily: {daily_pct:.1f}% (${stats['daily_cost']:.2f} / ${self.daily_budget:.2f})")
        
        if self.monthly_budget < float('inf'):
            monthly_pct = (stats['monthly_cost'] / self.monthly_budget * 100)
            print(f"   Monthly: {monthly_pct:.1f}% (${stats['monthly_cost']:.2f} / ${self.monthly_budget:.2f})")
        
        print("=" * 60 + "\n")


# Global tracker instance
_tracker = None

def get_tracker() -> CostTracker:
    """Get global cost tracker instance"""
    global _tracker
    if _tracker is None:
        _tracker = CostTracker()
    return _tracker


if __name__ == "__main__":
    # Demo
    tracker = CostTracker()
    tracker.set_budgets(daily=10.0, monthly=200.0)
    
    # Simulate some calls
    tracker.record("github_models", "gpt-4o", 1000, 500)
    tracker.record("anthropic", "claude-3.7-sonnet", 2000, 1000)
    tracker.record("openai", "gpt-4o", 1500, 800)
    
    tracker.print_summary()