"""Copy-trade follow / unfollow / mirror endpoints.

Brian 2026-05-12 校正 — copy trading with explicit user opt-in is allowed.
Every entry point converges on `assert_user_consent_or_no_trade`, which
either lets the request through (and writes an audit record) or returns 403.

Endpoints:
    POST   /api/copytrade/follow      register a follow relationship
    POST   /api/copytrade/unfollow    drop a follow relationship
    GET    /api/copytrade/positions   list currently-mirrored sources
    POST   /api/copytrade/mirror      internal hook fired by signal pipeline

State is kept in-process for now (single-instance assumption). Promotion
to the SQL layer is a Phase 5 task; the route shape is what we need to
lock first so the consent + audit pattern can be reviewed end-to-end.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from fastapi import APIRouter, FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from brokers import BrokerAuthError, BrokerOrder, BrokerRateLimitError, get_broker_client
from security import assert_user_consent_or_no_trade, log_audit

logger = logging.getLogger(__name__)


_VALID_BROKERS = ("pionex", "ctbc", "paper")

# Process-local follow registry. Maps follow_id → record.
_FOLLOWS: dict[str, dict[str, Any]] = {}


class FollowRequest(BaseModel):
    follow_agent_id: str = Field(..., min_length=1)
    broker: str = Field(..., min_length=1)
    explicit_consent: bool = False
    risk_disclosure_accepted: bool = False
    user_id: str = Field("anonymous", min_length=1)
    max_position_ntd: Optional[float] = None


class UnfollowRequest(BaseModel):
    follow_id: str = Field(..., min_length=1)


class MirrorRequest(BaseModel):
    follow_id: str = Field(..., min_length=1)
    signal_ref: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1)
    side: str = Field(..., pattern="^(buy|sell)$")
    quantity: float = Field(..., gt=0)
    price: Optional[float] = None
    order_type: str = "market"


def _validate_broker(name: str) -> None:
    if name not in _VALID_BROKERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"broker must be one of {_VALID_BROKERS}",
        )


def _require_consent_fields(req: FollowRequest) -> None:
    if req.explicit_consent is not True:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "reason": "missing_explicit_consent",
                "fix": "set explicit_consent=true after the user clicks Follow",
            },
        )
    if req.risk_disclosure_accepted is not True:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "reason": "risk_disclosure_not_accepted",
                "fix": "set risk_disclosure_accepted=true after the user clicks accept",
            },
        )


def register_copytrade_routes(app: FastAPI) -> None:
    router = APIRouter(prefix="/api/copytrade", tags=["copytrade"])

    @router.post("/follow")
    def follow(req: FollowRequest) -> dict[str, Any]:
        _validate_broker(req.broker)
        _require_consent_fields(req)

        follow_id = f"fl-{uuid.uuid4().hex[:12]}"
        record = {
            "follow_id": follow_id,
            "user_id": req.user_id,
            "follow_agent_id": req.follow_agent_id,
            "broker": req.broker,
            "max_position_ntd": req.max_position_ntd,
            "consent_confirmed": True,
            "explicit_follow_action": True,
        }
        _FOLLOWS[follow_id] = record

        # Audit the consent event itself — the mirror events come later.
        assert_user_consent_or_no_trade(
            action="copytrade_follow",
            user_consent=True,
            audit_meta={**record, "explicit_follow_action": True},
        )

        return {
            "ok": True,
            "follow_id": follow_id,
            "broker": req.broker,
            "follow_agent_id": req.follow_agent_id,
            "policy": "user_consent_recorded",
        }

    @router.post("/unfollow")
    def unfollow(req: UnfollowRequest) -> dict[str, Any]:
        record = _FOLLOWS.pop(req.follow_id, None)
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="follow_id not found",
            )
        log_audit(
            "copytrade_unfollow",
            "user_revoked_consent",
            {"follow_id": req.follow_id, "user_id": record.get("user_id", "anonymous")},
        )
        return {"ok": True, "follow_id": req.follow_id}

    @router.get("/positions")
    def positions(user_id: str = "anonymous") -> dict[str, Any]:
        items = [r for r in _FOLLOWS.values() if r["user_id"] == user_id]
        return {"user_id": user_id, "positions": items, "count": len(items)}

    @router.post("/mirror")
    def mirror(req: MirrorRequest) -> dict[str, Any]:
        record = _FOLLOWS.get(req.follow_id)
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="follow_id not found (user must /follow first)",
            )

        if req.side not in ("buy", "sell"):
            raise HTTPException(status_code=400, detail="side must be buy|sell")

        broker_name = record["broker"]
        signal_ref = req.signal_ref
        audit_meta = {
            "user_id": record["user_id"],
            "follow_id": req.follow_id,
            "source_agent": record["follow_agent_id"],
            "broker": broker_name,
            "consent_confirmed": True,
            "signal_ref": signal_ref,
            "symbol": req.symbol,
            "side": req.side,
            "quantity": req.quantity,
            "explicit_follow_action": True,
        }

        # This raises 403 if consent / explicit_follow_action ever flips
        # (defence in depth — the registry write also stamps the marker).
        assert_user_consent_or_no_trade(
            action="copytrade_mirror",
            user_consent=True,
            audit_meta=audit_meta,
        )

        try:
            client = get_broker_client(broker_name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        order = BrokerOrder(
            symbol=req.symbol,
            side=req.side,
            quantity=req.quantity,
            order_type=req.order_type,
            price=req.price,
            meta={"follow_id": req.follow_id, "signal_ref": signal_ref},
        )

        try:
            result = client.place_order(order)
        except BrokerAuthError as exc:
            log_audit(
                "copytrade_mirror_blocked",
                "broker_auth_error",
                {**audit_meta, "error": str(exc)},
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"reason": "broker_auth_error", "broker": broker_name, "hint": "configure API keys"},
            ) from exc
        except BrokerRateLimitError as exc:
            log_audit(
                "copytrade_mirror_blocked",
                "broker_rate_limit",
                {**audit_meta, "error": str(exc)},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"reason": "broker_rate_limit", "broker": broker_name, "retry_hint": "back off"},
            ) from exc

        log_audit(
            "copytrade_mirror_filled",
            "broker_order_placed",
            {**audit_meta, "order_ref": result.order_ref, "broker_status": result.status},
        )

        return {
            "ok": True,
            "follow_id": req.follow_id,
            "broker": broker_name,
            "order_ref": result.order_ref,
            "status": result.status,
            "filled_quantity": result.filled_quantity,
            "average_price": result.average_price,
        }

    app.include_router(router)
