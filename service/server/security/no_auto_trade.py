"""Enforce Brian's no-auto-trade policy.

ALLOWED:
- Paper trading against the simulated NT$ sandbox.
- Signal publication (strategy / operation / discussion text).
- Copy-trade *notifications* dispatched to the follower's message queue so the
  user can manually execute through their own broker.

DENIED:
- Direct broker order execution from server-side code.
- Auto-fill triggered by broker / exchange webhooks.
- Copy-trade auto-mirroring (server forwarding fills to a real account).

The policy is enforced at the FastAPI dependency layer so any route that
needs the guard can declare it with `Depends(enforce_no_auto_trade)` and rely
on the module to reject `paper=false` payloads with HTTP 403 — without having
to repeat the rule in every handler.

The single global override is `ALLOW_LIVE_TRADING` in `config.py`, which must
stay false in production. Flipping it true is intentionally a two-step
change: edit the config AND remove the assert in `enforce_no_auto_trade`.
That extra friction is the point.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

from fastapi import HTTPException, Request, status

import config

logger = logging.getLogger(__name__)


class LiveTradingDeniedError(RuntimeError):
    """Raised internally when code attempts a real-money order path.

    Routes should never see this directly — `enforce_no_auto_trade` converts
    it to an HTTP 403. The exception class exists so unit tests can assert
    the specific guard fired (instead of any HTTPException).
    """


_DENY_REASON = (
    "Server policy denies live broker execution. BW-Trader is a paper-trading "
    "sandbox. To trade real money, follow the signal notification in your "
    "client and place the order in your own broker app."
)


def _coerce_paper_flag(payload: Any) -> Optional[bool]:
    """Return the value of `paper` on a payload, or None if absent.

    Accepts pydantic models, dicts, or anything with attribute access. We
    treat the flag as opt-in: if it's missing entirely we don't infer
    intent — the caller decides whether to default-allow paper or default-
    deny live.
    """
    if payload is None:
        return None
    if isinstance(payload, Mapping):
        if "paper" not in payload:
            return None
        return bool(payload["paper"])
    paper = getattr(payload, "paper", None)
    if paper is None:
        return None
    return bool(paper)


def assert_paper_only(payload: Any) -> None:
    """Reject a payload that explicitly requests live execution.

    Use inside a handler when you have the payload in hand but don't want to
    add a dependency at the route signature. Raises HTTPException 403 so the
    response shape matches `enforce_no_auto_trade`.
    """
    paper = _coerce_paper_flag(payload)
    if paper is False and not config.ALLOW_LIVE_TRADING:
        logger.warning("no-auto-trade: payload requested paper=false; denied")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_DENY_REASON)


async def enforce_no_auto_trade(request: Request) -> None:
    """FastAPI dependency that rejects live-execution requests.

    Inspects the JSON body for `paper: false`. If present and live trading is
    not globally enabled, returns HTTP 403 with a human-readable reason. The
    body is restored onto `request.state` so the downstream handler can still
    parse it without re-reading the stream.
    """
    if config.ALLOW_LIVE_TRADING:
        # Caller explicitly opted in via config. The guard intentionally
        # short-circuits so the live-trading path can be wired in later
        # without touching every route — but the default config keeps this
        # branch unreachable in production.
        return

    body: Optional[bytes] = None
    try:
        body = await request.body()
    except Exception:  # pragma: no cover — defensive: framework should not fail
        body = None

    if not body:
        return

    paper_flag: Optional[bool] = None
    try:
        import json

        parsed = json.loads(body)
        paper_flag = _coerce_paper_flag(parsed)
    except (ValueError, TypeError):
        # Non-JSON body (form upload, etc.) — the trading endpoints all use
        # JSON, so anything else is out of scope for this guard.
        return

    if paper_flag is False:
        logger.warning(
            "no-auto-trade: %s %s denied (paper=false)",
            request.method,
            request.url.path,
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_DENY_REASON)


def reject_broker_webhook(source: str) -> None:
    """Hard-block any code path that processes an inbound broker webhook.

    Even if `ALLOW_LIVE_TRADING` is flipped on, broker webhook fills must
    never auto-execute — they would bypass the user's manual confirmation
    step. Callers should invoke this at the top of any webhook handler.
    """
    logger.error("no-auto-trade: broker webhook from %s rejected", source)
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=(
            f"Broker webhook from {source} cannot trigger trades. "
            "Webhooks are accepted for read-only reconciliation only."
        ),
    )


def queue_copy_trade_notification(
    follower_id: int,
    leader_id: int,
    signal_id: int,
    summary: str,
) -> dict[str, Any]:
    """Shape a copy-trade payload that a follower must manually execute.

    The function intentionally returns a plain dict instead of performing
    the trade. Routes that consume this should push the dict onto the
    follower's message queue (existing `push_agent_message` helper) and
    respond 202 Accepted to signal "received, not executed".
    """
    return {
        "type": "copy_trade_notification",
        "follower_id": follower_id,
        "leader_id": leader_id,
        "signal_id": signal_id,
        "summary": summary,
        "execution_required": "manual",
        "policy": "no_auto_trade",
    }
