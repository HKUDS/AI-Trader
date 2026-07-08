"""Token usage routes.

Agents self-report LLM token usage per call; the platform aggregates it by
model and by UTC day (issue #74). Writes and per-agent reads are scoped to the
authenticated agent; the model overview is a read-only, agent-anonymous rollup
(short-cached) so anyone can see how the models are used.
"""

import time
from datetime import date
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Query

from permissions import require_agent
from routes_models import TokenUsageBatchReport, TokenUsageReport
from routes_shared import (
    TOKEN_USAGE_OVERVIEW_CACHE_KEY_PREFIX,
    TOKEN_USAGE_OVERVIEW_CACHE_TTL_SECONDS,
    RouteContext,
    get_short_cached_payload,
    set_short_cached_payload,
)
from token_usage import (
    get_usage_by_model_and_day,
    is_valid_usage_date,
    record_token_usage,
    record_token_usage_batch,
    summarize_usage,
)

TOKEN_USAGE_REPORT_WINDOW_SECONDS = 60
TOKEN_USAGE_REPORT_WINDOW_LIMIT = 120
TOKEN_USAGE_RATE_LIMIT_MAX_AGENTS = 10000


def register_token_usage_routes(app: FastAPI, ctx: RouteContext) -> None:
    @app.post('/api/claw/usage')
    async def report_token_usage(data: TokenUsageReport, authorization: str = Header(None)):
        agent = require_agent(authorization)
        _enforce_token_usage_report_rate_limit(ctx, agent['id'])
        record = record_token_usage(
            agent_id=agent['id'],
            model=data.model,
            provider=data.provider or '',
            input_tokens=data.input_tokens,
            output_tokens=data.output_tokens,
            client_event_id=data.client_event_id,
        )
        return {'success': True, 'usage': record}

    @app.post('/api/claw/usage/batch')
    async def report_token_usage_batch(data: TokenUsageBatchReport, authorization: str = Header(None)):
        # One batch counts as one write, so a busy agent can report many calls
        # in a single request without the rate limit dropping usage.
        agent = require_agent(authorization)
        _enforce_token_usage_report_rate_limit(ctx, agent['id'])
        records = record_token_usage_batch(
            agent_id=agent['id'],
            reports=[report.model_dump() for report in data.reports],
        )
        return {'success': True, 'count': len(records), 'usage': records}

    @app.get('/api/claw/usage')
    async def get_my_token_usage(
        start_date: Optional[str] = Query(None),
        end_date: Optional[str] = Query(None),
        authorization: str = Header(None),
    ):
        agent = require_agent(authorization)
        start, end = _validated_date_range(start_date, end_date)
        rows = get_usage_by_model_and_day(agent_id=agent['id'], start_date=start, end_date=end)
        return {'agent_id': agent['id'], 'usage': rows, 'totals': summarize_usage(rows), 'timezone': 'UTC'}

    @app.get('/api/usage/models')
    async def get_model_usage_overview(
        start_date: Optional[str] = Query(None),
        end_date: Optional[str] = Query(None),
    ):
        start, end = _validated_date_range(start_date, end_date)
        cache_key = f"{TOKEN_USAGE_OVERVIEW_CACHE_KEY_PREFIX}:start={start or ''}:end={end or ''}"
        cached = get_short_cached_payload(
            ctx, ctx.token_usage_overview_cache, cache_key, TOKEN_USAGE_OVERVIEW_CACHE_TTL_SECONDS
        )
        if cached is not None:
            return cached

        rows = get_usage_by_model_and_day(start_date=start, end_date=end)
        payload = {'usage': rows, 'totals': summarize_usage(rows), 'timezone': 'UTC'}
        return set_short_cached_payload(
            ctx, ctx.token_usage_overview_cache, cache_key, payload, TOKEN_USAGE_OVERVIEW_CACHE_TTL_SECONDS
        )


def _validated_date_range(
    start_date: Optional[str],
    end_date: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    """Reject malformed date filters before they reach the query. Fail closed."""
    parsed_start = _parse_usage_query_date(start_date)
    parsed_end = _parse_usage_query_date(end_date)
    if parsed_start is not None and parsed_end is not None and parsed_start > parsed_end:
        raise HTTPException(status_code=400, detail='start_date must be before or equal to end_date')
    return start_date, end_date


def _parse_usage_query_date(value: Optional[str]) -> Optional[date]:
    if value is None:
        return None
    if not is_valid_usage_date(value):
        raise HTTPException(status_code=400, detail='Dates must use YYYY-MM-DD format')
    return date.fromisoformat(value)


def _enforce_token_usage_report_rate_limit(ctx: RouteContext, agent_id: int) -> None:
    """Bound self-reported usage writes from each authenticated agent."""
    now_ts = time.time()
    state = ctx.token_usage_rate_limit_state
    recent_timestamps = [
        timestamp
        for timestamp in state.get(agent_id, [])
        if now_ts - timestamp < TOKEN_USAGE_REPORT_WINDOW_SECONDS
    ]
    if len(recent_timestamps) >= TOKEN_USAGE_REPORT_WINDOW_LIMIT:
        raise HTTPException(status_code=429, detail='Token usage report rate limit reached. Please slow down.')
    recent_timestamps.append(now_ts)
    state[agent_id] = recent_timestamps

    if len(state) > TOKEN_USAGE_RATE_LIMIT_MAX_AGENTS:
        _prune_idle_rate_limit_agents(state, now_ts)


def _prune_idle_rate_limit_agents(state: dict[int, list[float]], now_ts: float) -> None:
    """Drop agents whose most recent report is older than the window."""
    idle_agent_ids = [
        candidate_id
        for candidate_id, timestamps in state.items()
        if not timestamps or now_ts - timestamps[-1] >= TOKEN_USAGE_REPORT_WINDOW_SECONDS
    ]
    for candidate_id in idle_agent_ids:
        state.pop(candidate_id, None)
