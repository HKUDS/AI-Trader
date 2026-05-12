"""Security policy modules for BW-Trader.

Currently exposes only `no_auto_trade`, the dependency that enforces Brian's
red line: the server may not execute real broker orders. Other policy modules
(rate limits, auth shape, etc.) live elsewhere — this package is for the
small, load-bearing guardrails that the rest of the code base has to clear.
"""

from .no_auto_trade import (
    LiveTradingDeniedError,
    assert_paper_only,
    assert_user_consent_or_no_trade,
    enforce_no_auto_trade,
    log_audit,
    reject_broker_webhook,
    queue_copy_trade_notification,
)

__all__ = [
    "LiveTradingDeniedError",
    "assert_paper_only",
    "assert_user_consent_or_no_trade",
    "enforce_no_auto_trade",
    "log_audit",
    "reject_broker_webhook",
    "queue_copy_trade_notification",
]
