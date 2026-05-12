"""Security-policy HTTP surface.

Exposes a single explicit endpoint that any inbound broker / exchange
webhook would hit. The handler hard-rejects so the system has an obvious,
audit-friendly answer for "where do brokers post fills?": nowhere.

Keeping this in its own module makes the policy visible at the route layer
and gives ops a single place to point legal / compliance at when reviewing
the no-auto-trade red line.
"""

from __future__ import annotations

from fastapi import FastAPI, Request

from security import reject_broker_webhook


def register_security_routes(app: FastAPI) -> None:
    @app.post('/api/brokers/webhook')
    async def broker_webhook(request: Request):
        source = request.headers.get('X-Broker-Source', 'unknown')
        reject_broker_webhook(source)

    @app.post('/api/brokers/{source}/webhook')
    async def broker_webhook_named(source: str):
        reject_broker_webhook(source)

    @app.get('/api/policy/no-auto-trade')
    async def describe_policy():
        return {
            'policy': 'no_system_autonomous_trade',
            'last_revised': '2026-05-12',
            'allowed': [
                'paper_trading_ntd_sandbox',
                'signal_publication',
                'copy_trade_notification_to_follower_queue',
                'copy_trade_mirror_with_explicit_user_consent_and_risk_disclosure',
            ],
            'denied': [
                'agent_autonomous_broker_execution',
                'broker_webhook_triggered_fills',
                'scheduled_or_system_initiated_mirror_trade',
                'copy_trade_mirror_without_explicit_consent',
            ],
            'consent_endpoint': '/api/copytrade/follow',
            'consent_requirements': [
                'explicit_consent=true',
                'risk_disclosure_accepted=true',
                'audit_log_record_written',
            ],
            'enforcement': 'fastapi_dependency_layer + assert_user_consent_or_no_trade',
        }
