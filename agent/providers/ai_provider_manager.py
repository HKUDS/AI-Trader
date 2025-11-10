"""
AI Provider Manager - Multi-provider AI API support with failover

Supports:
- GitHub Models (Free, Priority 1)
- Anthropic Claude (Priority 2)
- OpenAI GPT (Priority 3)

Features:
- Automatic failover on rate limits
- Cost tracking
- Load balancing
"""

import os
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()


@dataclass
class ProviderConfig:
    """Configuration for an AI provider"""
    name: str
    base_url: str
    api_key: str
    priority: int
    rate_limit_per_min: int
    rate_limit_per_day: int
    cost_per_1k_tokens: float
    enabled: bool = True


@dataclass
class ProviderStats:
    """Statistics for a provider"""
    total_requests: int = 0
    failed_requests: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    last_request_time: Optional[datetime] = None
    requests_this_minute: int = 0
    requests_today: int = 0
    minute_reset_time: Optional[datetime] = None
    day_reset_time: Optional[datetime] = None


class AIProviderManager:
    """
    Manage multiple AI providers with automatic failover
    """
    
    def __init__(self):
        """Initialize provider manager"""
        self.providers: Dict[str, ProviderConfig] = {}
        self.stats: Dict[str, ProviderStats] = {}
        self.current_provider: Optional[str] = None
        
        # Initialize providers
        self._init_providers()
    
    def _init_providers(self):
        """Initialize all available providers"""
        
        # GitHub Models (Free)
        if os.getenv("OPENAI_API_KEY", "").startswith("ghp_"):
            self.providers["github_models"] = ProviderConfig(
                name="GitHub Models",
                base_url="https://models.inference.ai.azure.com",
                api_key=os.getenv("OPENAI_API_KEY"),
                priority=1,
                rate_limit_per_min=15,
                rate_limit_per_day=150,
                cost_per_1k_tokens=0.0,  # Free!
                enabled=True
            )
            self.stats["github_models"] = ProviderStats()
            print("✅ GitHub Models provider initialized (FREE)")
        
        # Anthropic Claude
        if os.getenv("ANTHROPIC_API_KEY"):
            self.providers["anthropic"] = ProviderConfig(
                name="Anthropic Claude",
                base_url="https://api.anthropic.com",
                api_key=os.getenv("ANTHROPIC_API_KEY"),
                priority=2,
                rate_limit_per_min=50,
                rate_limit_per_day=10000,
                cost_per_1k_tokens=0.003,  # $0.003 per 1K tokens
                enabled=True
            )
            self.stats["anthropic"] = ProviderStats()
            print("✅ Anthropic Claude provider initialized")
        
        # OpenAI
        if os.getenv("OPENAI_API_KEY") and not os.getenv("OPENAI_API_KEY").startswith("ghp_"):
            self.providers["openai"] = ProviderConfig(
                name="OpenAI",
                base_url=os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1"),
                api_key=os.getenv("OPENAI_API_KEY"),
                priority=3,
                rate_limit_per_min=500,
                rate_limit_per_day=100000,
                cost_per_1k_tokens=0.005,  # $0.005 per 1K tokens (GPT-4o)
                enabled=True
            )
            self.stats["openai"] = ProviderStats()
            print("✅ OpenAI provider initialized")
        
        if not self.providers:
            raise ValueError("❌ No AI providers configured! Check your .env file.")
        
        print(f"📊 Total providers available: {len(self.providers)}")
    
    def get_best_provider(self) -> Optional[ProviderConfig]:
        """
        Get the best available provider based on:
        - Priority
        - Rate limits
        - Availability
        
        Returns:
            ProviderConfig or None if no provider available
        """
        # Sort providers by priority
        sorted_providers = sorted(
            self.providers.items(),
            key=lambda x: x[1].priority
        )
        
        for provider_id, config in sorted_providers:
            if not config.enabled:
                continue
            
            # Check rate limits
            if self._check_rate_limit(provider_id):
                self.current_provider = provider_id
                print(f"🤖 Using provider: {config.name} (Priority {config.priority})")
                return config
        
        print("❌ No available providers! All rate limits exceeded.")
        return None
    
    def _check_rate_limit(self, provider_id: str) -> bool:
        """
        Check if provider is within rate limits
        
        Args:
            provider_id: Provider identifier
            
        Returns:
            True if within limits, False otherwise
        """
        config = self.providers[provider_id]
        stats = self.stats[provider_id]
        now = datetime.now()
        
        # Reset minute counter if needed
        if stats.minute_reset_time is None or now >= stats.minute_reset_time:
            stats.requests_this_minute = 0
            stats.minute_reset_time = now + timedelta(minutes=1)
        
        # Reset daily counter if needed
        if stats.day_reset_time is None or now >= stats.day_reset_time:
            stats.requests_today = 0
            stats.day_reset_time = now + timedelta(days=1)
        
        # Check limits
        if stats.requests_this_minute >= config.rate_limit_per_min:
            print(f"⚠️ {config.name}: Minute rate limit reached ({stats.requests_this_minute}/{config.rate_limit_per_min})")
            return False
        
        if stats.requests_today >= config.rate_limit_per_day:
            print(f"⚠️ {config.name}: Daily rate limit reached ({stats.requests_today}/{config.rate_limit_per_day})")
            return False
        
        return True
    
    def record_request(
        self,
        provider_id: str,
        tokens: int,
        success: bool = True
    ):
        """
        Record a request to a provider
        
        Args:
            provider_id: Provider identifier
            tokens: Number of tokens used
            success: Whether request was successful
        """
        if provider_id not in self.stats:
            return
        
        stats = self.stats[provider_id]
        config = self.providers[provider_id]
        
        stats.total_requests += 1
        stats.requests_this_minute += 1
        stats.requests_today += 1
        stats.last_request_time = datetime.now()
        
        if success:
            stats.total_tokens += tokens
            stats.total_cost += (tokens / 1000) * config.cost_per_1k_tokens
        else:
            stats.failed_requests += 1
        
        # Log
        print(f"📊 {config.name} request recorded:")
        print(f"   - Tokens: {tokens}")
        print(f"   - Cost: ${(tokens / 1000) * config.cost_per_1k_tokens:.4f}")
        print(f"   - Total today: {stats.requests_today}/{config.rate_limit_per_day}")
    
    def get_provider_config(self, provider_id: str) -> Optional[ProviderConfig]:
        """Get configuration for a specific provider"""
        return self.providers.get(provider_id)
    
    def get_stats(self, provider_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get statistics for provider(s)
        
        Args:
            provider_id: Specific provider, or None for all
            
        Returns:
            Statistics dictionary
        """
        if provider_id:
            if provider_id in self.stats:
                stats = self.stats[provider_id]
                config = self.providers[provider_id]
                return {
                    "provider": config.name,
                    "total_requests": stats.total_requests,
                    "failed_requests": stats.failed_requests,
                    "success_rate": (
                        (stats.total_requests - stats.failed_requests) / stats.total_requests * 100
                        if stats.total_requests > 0 else 0
                    ),
                    "total_tokens": stats.total_tokens,
                    "total_cost": stats.total_cost,
                    "requests_today": stats.requests_today,
                    "rate_limit_day": config.rate_limit_per_day
                }
            return {}
        
        # Return stats for all providers
        return {
            provider_id: self.get_stats(provider_id)
            for provider_id in self.stats.keys()
        }
    
    def print_summary(self):
        """Print summary of all providers"""
        print(f"\n{'='*60}")
        print(f"🤖 AI PROVIDER SUMMARY")
        print(f"{'='*60}")
        
        for provider_id, config in sorted(
            self.providers.items(),
            key=lambda x: x[1].priority
        ):
            stats = self.stats[provider_id]
            
            print(f"\n{config.name} (Priority {config.priority}):")
            print(f"   - Status: {'✅ Enabled' if config.enabled else '❌ Disabled'}")
            print(f"   - Total requests: {stats.total_requests}")
            print(f"   - Failed requests: {stats.failed_requests}")
            print(f"   - Success rate: {((stats.total_requests - stats.failed_requests) / stats.total_requests * 100) if stats.total_requests > 0 else 0:.1f}%")
            print(f"   - Total tokens: {stats.total_tokens:,}")
            print(f"   - Total cost: ${stats.total_cost:.4f}")
            print(f"   - Today: {stats.requests_today}/{config.rate_limit_per_day}")
            print(f"   - Rate: ${config.cost_per_1k_tokens}/1K tokens")
        
        print(f"\n{'='*60}\n")