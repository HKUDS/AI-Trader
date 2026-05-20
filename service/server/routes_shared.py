import json
import math
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException, WebSocket
from zoneinfo import ZoneInfo

from database import get_db_connection


GROUPED_SIGNALS_CACHE_TTL_SECONDS = 30
AGENT_SIGNALS_CACHE_TTL_SECONDS = 15
PRICE_API_RATE_LIMIT = 1.0
PRICE_QUOTE_CACHE_TTL_SECONDS = 10
MAX_ABS_PROFIT_DISPLAY = 1e12
LEADERBOARD_CACHE_TTL_SECONDS = 60
DISCUSSION_COOLDOWN_SECONDS = 60
REPLY_COOLDOWN_SECONDS = 20
DISCUSSION_WINDOW_SECONDS = 600
REPLY_WINDOW_SECONDS = 300
DISCUSSION_WINDOW_LIMIT = 5
REPLY_WINDOW_LIMIT = 10
CONTENT_DUPLICATE_WINDOW_SECONDS = 1800
ACCEPT_REPLY_REWARD = 3
EXPERIMENT_UNREAD_PREVIEW_LIMIT = 3
EXPERIMENT_NOTICE_EXPOSURE_EVENT_TTL_SECONDS = 1800
EXPERIMENT_READ_ENDPOINT = '/api/claw/messages/read-experiment'
EXPERIMENT_NOTIFICATION_TYPES = (
    'experiment_announcement',
    'experiment_assignment',
    'experiment_reminder',
    'experiment_rule_update',
    'experiment_result_update',
    'challenge_invite',
    'team_mission_invite',
)

TRENDING_CACHE_KEY = 'trending:top20'
LEADERBOARD_CACHE_KEY_PREFIX = 'leaderboard:profit_history'
GROUPED_SIGNALS_CACHE_KEY_PREFIX = 'signals:grouped'
AGENT_SIGNALS_CACHE_KEY_PREFIX = 'signals:agent'
SIGNAL_FEED_CACHE_KEY_PREFIX = 'signals:feed'
PRICE_CACHE_KEY_PREFIX = 'price:quote'
MARKET_INTEL_CACHE_KEY_PREFIX = 'market_intel'
PUBLIC_COUNT_CACHE_KEY_PREFIX = 'public_counts'
AGENT_MESSAGE_SUMMARY_CACHE_KEY_PREFIX = 'agent_messages:unread_summary'
EXPERIMENT_NOTICE_CACHE_KEY_PREFIX = 'experiment_notice'
MARKET_INTEL_CACHE_TTL_SECONDS = 30
PUBLIC_COUNT_CACHE_TTL_SECONDS = 30
AGENT_MESSAGE_SUMMARY_CACHE_TTL_SECONDS = 5
EXPERIMENT_NOTICE_CACHE_TTL_SECONDS = 5
SIGNAL_FEED_CACHE_TTL_SECONDS = 10
POSITIONS_CACHE_TTL_SECONDS = 10

MENTION_PATTERN = re.compile(r'@([A-Za-z0-9_\-]{2,64})')
_EXPERIMENT_NOTICE_EXPOSURE_EVENT_CACHE: dict[tuple[int, str, str], float] = {}
SUPPORTED_MARKETS = {'us-stock', 'crypto', 'polymarket'}
MARKET_ALIASES = {
    'binance': 'crypto',
    'binance-spot': 'crypto',
    'binance_spot': 'crypto',
    'coinbase': 'crypto',
    'coinbase-spot': 'crypto',
    'coinbase_spot': 'crypto',
    'hyperliquid': 'crypto',
    'hl': 'crypto',
    'kraken': 'crypto',
    'okx': 'crypto',
    'solusdt': 'crypto',
    'stock': 'us-stock',
    'stocks': 'us-stock',
    'us': 'us-stock',
    'us stock': 'us-stock',
    'us stocks': 'us-stock',
    'us_stock': 'us-stock',
    'us_stocks': 'us-stock',
    'us-premarket': 'us-stock',
    'us-aftermarket': 'us-stock',
    'usstock': 'us-stock',
    'nasdaq': 'us-stock',
    'sp500': 'us-stock',
    'etf': 'us-stock',
    'equity': 'us-stock',
    'equities': 'us-stock',
}


def normalize_market(market: str | None) -> str:
    normalized = (market or 'us-stock').strip().lower()
    return MARKET_ALIASES.get(normalized, normalized)


def validate_market(market: str | None) -> str:
    normalized = normalize_market(market)
    if normalized not in SUPPORTED_MARKETS:
        allowed = ', '.join(sorted(SUPPORTED_MARKETS))
        raise HTTPException(status_code=400, detail=f"Unsupported market '{market}'. Supported markets: {allowed}")
    return normalized


def allow_sync_price_fetch_in_api() -> bool:
    return os.getenv('ALLOW_SYNC_PRICE_FETCH_IN_API', 'false').strip().lower() in {'1', 'true', 'yes', 'on'}


def api_access_log_enabled() -> bool:
    return os.getenv('API_ACCESS_LOG', 'false').strip().lower() in {'1', 'true', 'yes', 'on'}


def should_fetch_server_trade_price(market: str) -> bool:
    normalized_market = normalize_market(market)
    if normalized_market in {'crypto', 'polymarket', 'us-stock'}:
        return True
    return allow_sync_price_fetch_in_api()


@dataclass
class RouteContext:
    grouped_signals_cache: dict[tuple[str, str, int, int], tuple[float, dict[str, Any]]] = field(default_factory=dict)
    signal_feed_cache: dict[tuple[str, str, str, int, int, str, int], tuple[float, dict[str, Any]]] = field(default_factory=dict)
    agent_signals_cache: dict[tuple[int, str, int], tuple[float, dict[str, Any]]] = field(default_factory=dict)
    positions_cache: dict[int, tuple[float, dict[str, Any]]] = field(default_factory=dict)
    price_api_last_request: dict[int, float] = field(default_factory=dict)
    price_quote_cache: dict[tuple[str, str, str, str], tuple[float, dict[str, Any]]] = field(default_factory=dict)
    leaderboard_cache: dict[tuple[int, int, int, bool], tuple[float, dict[str, Any]]] = field(default_factory=dict)
    market_intel_cache: dict[str, tuple[float, dict[str, Any]]] = field(default_factory=dict)
    public_count_cache: dict[str, tuple[float, dict[str, Any]]] = field(default_factory=dict)
    agent_message_summary_cache: dict[str, tuple[float, dict[str, Any]]] = field(default_factory=dict)
    experiment_notice_cache: dict[int, tuple[float, Optional[dict[str, Any]]]] = field(default_factory=dict)
    content_rate_limit_state: dict[tuple[int, str], dict[str, Any]] = field(default_factory=dict)
    ws_connections: dict[int, WebSocket] = field(default_factory=dict)
    verification_codes: dict[str, dict[str, Any]] = field(default_factory=dict)
    agent_token_recovery_requests: dict[int, dict[str, Any]] = field(default_factory=dict)


def format_polymarket_reference(reference: str) -> str:
    ref = (reference or '').strip()
    if not ref:
        return ''
    if ref.startswith('0x') or ref.isdigit():
        return ref
    return ref.replace('-', ' ')


def decorate_polymarket_item(item: dict, fetch_remote: bool = False) -> dict:
    if item.get('market') != 'polymarket':
        return item

    description = None
    if fetch_remote:
        try:
            from price_fetcher import describe_polymarket_contract

            description = describe_polymarket_contract(
                item.get('symbol') or '',
                token_id=item.get('token_id'),
                outcome=item.get('outcome'),
            )
        except Exception:
            description = None

    if not description:
        fallback = format_polymarket_reference(item.get('symbol') or '')
        outcome = item.get('outcome')
        item['display_title'] = f'{fallback} [{outcome}]' if fallback and outcome else fallback
        item['market_title'] = fallback or (item.get('symbol') or '')
        return item

    item['token_id'] = item.get('token_id') or description.get('token_id')
    item['outcome'] = item.get('outcome') or description.get('outcome')
    item['market_title'] = description.get('market_title')
    item['market_slug'] = description.get('market_slug')
    item['display_title'] = description.get('display_title')
    return item


def clamp_profit_for_display(profit: float) -> float:
    if profit is None:
        return 0.0
    try:
        parsed = float(profit)
        if abs(parsed) > MAX_ABS_PROFIT_DISPLAY:
            return MAX_ABS_PROFIT_DISPLAY if parsed > 0 else -MAX_ABS_PROFIT_DISPLAY
        return parsed
    except (TypeError, ValueError):
        return 0.0


def check_price_api_rate_limit(ctx: RouteContext, agent_id: int) -> bool:
    now = datetime.now(timezone.utc).timestamp()
    last = ctx.price_api_last_request.get(agent_id, 0)
    if now - last >= PRICE_API_RATE_LIMIT:
        ctx.price_api_last_request[agent_id] = now
        return True
    return False


def utc_now_iso_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def get_short_cached_payload(
    ctx: RouteContext,
    local_cache: dict[Any, tuple[float, Any]],
    redis_key: str,
    ttl_seconds: int,
) -> Any:
    from cache import get_json

    now_ts = time.time()
    cached = local_cache.get(redis_key)
    if cached and now_ts - cached[0] < ttl_seconds:
        return cached[1]

    cached_payload = get_json(redis_key)
    if cached_payload is not None:
        local_cache[redis_key] = (now_ts, cached_payload)
        return cached_payload

    return None


def set_short_cached_payload(
    ctx: RouteContext,
    local_cache: dict[Any, tuple[float, Any]],
    redis_key: str,
    payload: Any,
    ttl_seconds: int,
) -> Any:
    from cache import set_json

    local_cache[redis_key] = (time.time(), payload)
    set_json(redis_key, payload, ttl_seconds=ttl_seconds)
    return payload


def invalidate_agent_message_caches(ctx: RouteContext, agent_id: int) -> None:
    from cache import delete

    ctx.agent_message_summary_cache.pop(f'{AGENT_MESSAGE_SUMMARY_CACHE_KEY_PREFIX}:agent_id={agent_id}', None)
    ctx.experiment_notice_cache.pop(agent_id, None)
    delete(f'{AGENT_MESSAGE_SUMMARY_CACHE_KEY_PREFIX}:agent_id={agent_id}')
    delete(f'{EXPERIMENT_NOTICE_CACHE_KEY_PREFIX}:agent_id={agent_id}:limit={EXPERIMENT_UNREAD_PREVIEW_LIMIT}')


def experiment_unread_notice(
    agent_id: int,
    *,
    limit: int = EXPERIMENT_UNREAD_PREVIEW_LIMIT,
    ctx: RouteContext | None = None,
) -> Optional[dict[str, Any]]:
    """Return a small non-destructive unread experiment notice for API responses."""
    limit = max(1, min(int(limit or EXPERIMENT_UNREAD_PREVIEW_LIMIT), 10))
    now_ts = time.time()
    redis_cache_key = f'{EXPERIMENT_NOTICE_CACHE_KEY_PREFIX}:agent_id={agent_id}:limit={limit}'
    if ctx is not None:
        cached = ctx.experiment_notice_cache.get(agent_id)
        if cached and now_ts - cached[0] < EXPERIMENT_NOTICE_CACHE_TTL_SECONDS:
            return cached[1]
        from cache import get_json

        cached_payload = get_json(redis_cache_key)
        if isinstance(cached_payload, dict) or cached_payload is None:
            if cached_payload is not None:
                notice = cached_payload.get('notice') if isinstance(cached_payload, dict) else None
                ctx.experiment_notice_cache[agent_id] = (now_ts, notice)
                return notice

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        placeholders = ','.join('?' for _ in EXPERIMENT_NOTIFICATION_TYPES)
        cursor.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM agent_messages
            WHERE agent_id = ? AND read = 0 AND type IN ({placeholders})
            """,
            (agent_id, *EXPERIMENT_NOTIFICATION_TYPES),
        )
        total = cursor.fetchone()['count']
        if not total:
            if ctx is not None:
                from cache import set_json

                ctx.experiment_notice_cache[agent_id] = (now_ts, None)
                set_json(redis_cache_key, {'notice': None}, ttl_seconds=EXPERIMENT_NOTICE_CACHE_TTL_SECONDS)
            return None

        cursor.execute(
            f"""
            SELECT id, type, content, data, created_at
            FROM agent_messages
            WHERE agent_id = ? AND read = 0 AND type IN ({placeholders})
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (agent_id, *EXPERIMENT_NOTIFICATION_TYPES, limit),
        )
        messages = []
        for row in cursor.fetchall():
            message = dict(row)
            if message.get('data'):
                try:
                    message['data'] = json.loads(message['data'])
                except Exception:
                    pass
            messages.append(message)
        message_ids = [message['id'] for message in messages if message.get('id') is not None]
        notice = {
            'unread_count': total,
            'requires_read': False,
            'read_receipts_role': 'diagnostic_only',
            'message_read_state_required': False,
            'reason': 'unread_experiment_messages',
            'messages': messages,
            'message_ids': message_ids,
            'recommended_action': {
                'method': 'POST',
                'endpoint': EXPERIMENT_READ_ENDPOINT,
                'headers': {'Authorization': 'Bearer <agent_token>'},
                'body': None,
                'marks_read': True,
                'description': 'Call this endpoint to receive unread experiment messages and mark them read in one step.',
            },
            'actions': [
                {
                    'name': 'read_experiment_messages',
                    'method': 'POST',
                    'endpoint': EXPERIMENT_READ_ENDPOINT,
                    'headers': {'Authorization': 'Bearer <agent_token>'},
                    'body': None,
                    'marks_read': True,
                },
                {
                    'name': 'read_and_mark_via_heartbeat',
                    'method': 'POST',
                    'endpoint': '/api/claw/agents/heartbeat',
                    'headers': {'Authorization': 'Bearer <agent_token>'},
                    'body': None,
                    'marks_read': True,
                },
                {
                    'name': 'fetch_recent_experiment_messages',
                    'method': 'GET',
                    'endpoint': '/api/claw/messages/recent?category=experiment&limit=10',
                    'headers': {'Authorization': 'Bearer <agent_token>'},
                    'body': None,
                    'marks_read': False,
                },
                {
                    'name': 'mark_experiment_messages_read',
                    'method': 'POST',
                    'endpoint': '/api/claw/messages/mark-read',
                    'headers': {'Authorization': 'Bearer <agent_token>'},
                    'body': {'categories': ['experiment']},
                    'marks_read': True,
                },
            ],
            'read_endpoints': [
                f'POST {EXPERIMENT_READ_ENDPOINT}',
                'POST /api/claw/agents/heartbeat',
                'GET /api/claw/messages/recent?category=experiment&limit=10',
            ],
            'mark_read_endpoint': {
                'method': 'POST',
                'endpoint': '/api/claw/messages/mark-read',
                'body': {'categories': ['experiment']},
            },
            'read_via': {
                'read_experiment': f'POST {EXPERIMENT_READ_ENDPOINT}',
                'heartbeat': 'POST /api/claw/agents/heartbeat',
                'recent': 'GET /api/claw/messages/recent?category=experiment&limit=10',
                'mark_read': 'POST /api/claw/messages/mark-read {"categories":["experiment"]}',
            },
            'note': f'Unread experiment messages are attached as diagnostics only. Experiment analysis now uses active behavior metrics; POST {EXPERIMENT_READ_ENDPOINT} remains available for explicit read receipts.',
        }
        if ctx is not None:
            from cache import set_json

            ctx.experiment_notice_cache[agent_id] = (now_ts, notice)
            set_json(redis_cache_key, {'notice': notice}, ttl_seconds=EXPERIMENT_NOTICE_CACHE_TTL_SECONDS)
        return notice
    finally:
        conn.close()


def _record_experiment_notice_exposed(agent_id: int, notice: dict[str, Any], *, surface: str) -> None:
    messages = notice.get('messages') or []
    message_ids = [message.get('id') for message in messages if message.get('id') is not None]
    message_types = sorted({message.get('type') for message in messages if message.get('type')})

    campaign_ids: set[str] = set()
    experiment_keys: set[str] = set()
    variant_keys: set[str] = set()
    for message in messages:
        data = message.get('data')
        if not isinstance(data, dict):
            continue
        if data.get('campaign_id'):
            campaign_ids.add(str(data['campaign_id']))
        if data.get('experiment_key'):
            experiment_keys.add(str(data['experiment_key']))
        if data.get('target_variant_key'):
            variant_keys.add(str(data['target_variant_key']))

    metadata = {
        'surface': surface,
        'unread_count': notice.get('unread_count'),
        'preview_count': len(messages),
        'message_ids': message_ids,
        'message_types': message_types,
        'campaign_ids': sorted(campaign_ids),
        'read_via': notice.get('read_via'),
    }
    experiment_key = next(iter(experiment_keys)) if len(experiment_keys) == 1 else None
    variant_key = next(iter(variant_keys)) if len(variant_keys) == 1 else None
    exposure_key = (
        agent_id,
        surface,
        ','.join(str(message_id) for message_id in message_ids) or ','.join(message_types),
    )
    now_ts = time.time()
    if now_ts - _EXPERIMENT_NOTICE_EXPOSURE_EVENT_CACHE.get(exposure_key, 0) < EXPERIMENT_NOTICE_EXPOSURE_EVENT_TTL_SECONDS:
        return
    _EXPERIMENT_NOTICE_EXPOSURE_EVENT_CACHE[exposure_key] = now_ts
    if len(_EXPERIMENT_NOTICE_EXPOSURE_EVENT_CACHE) > 10000:
        expired_before = now_ts - EXPERIMENT_NOTICE_EXPOSURE_EVENT_TTL_SECONDS
        for key, last_seen_at in list(_EXPERIMENT_NOTICE_EXPOSURE_EVENT_CACHE.items()):
            if last_seen_at < expired_before:
                _EXPERIMENT_NOTICE_EXPOSURE_EVENT_CACHE.pop(key, None)

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO experiment_events
            (event_id, event_type, actor_agent_id, target_agent_id, object_type, object_id,
             market, experiment_key, variant_key, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                'experiment_notice_exposed',
                agent_id,
                None,
                'agent',
                str(agent_id),
                None,
                experiment_key,
                variant_key,
                json.dumps(metadata, ensure_ascii=False, sort_keys=True, default=str),
                utc_now_iso_z(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def attach_experiment_unread_notice(
    payload: dict[str, Any],
    agent_id: int,
    *,
    surface: str = 'signals_write_response',
    field: str = 'experiment_unread',
    ctx: RouteContext | None = None,
) -> dict[str, Any]:
    notice = experiment_unread_notice(agent_id, ctx=ctx)
    if notice:
        must_call = {
            'method': 'POST',
            'endpoint': EXPERIMENT_READ_ENDPOINT,
            'headers': {'Authorization': 'Bearer <agent_token>'},
            'body': None,
            'marks_read': True,
        }
        payload[field] = notice
        payload['agent_notice'] = {
            **(payload.get('agent_notice') if isinstance(payload.get('agent_notice'), dict) else {}),
            'experiment_unread': True,
            'must_call': EXPERIMENT_READ_ENDPOINT,
            'must_call_method': 'POST',
            'must_call_now': False,
            'must_call_action': must_call,
            'required_action': {
                'type': 'read_experiment_messages',
                **must_call,
            },
            'read_receipts_role': 'diagnostic_only',
            'message_read_state_required': False,
            'primary_metric_family': 'active_agent_behavior',
            'reason': notice.get('reason'),
            'unread_count': notice.get('unread_count'),
            'message_ids': notice.get('message_ids', []),
            'messages': notice.get('messages', []),
            'recommended_action': notice.get('recommended_action'),
            'actions': notice.get('actions', []),
            'read_endpoints': notice.get('read_endpoints', []),
            'mark_read_endpoint': notice.get('mark_read_endpoint'),
            'read_via': notice.get('read_via', {}),
        }
        try:
            _record_experiment_notice_exposed(agent_id, notice, surface=surface)
        except Exception:
            pass
    return payload


def extract_mentions(content: str) -> list[str]:
    seen = set()
    for match in MENTION_PATTERN.findall(content or ''):
        normalized = match.strip()
        if normalized:
            seen.add(normalized)
    return list(seen)


def position_price_cache_key(row: Any) -> tuple[str, str, str, str]:
    return (
        str(row['symbol'] or ''),
        str(row['market'] or ''),
        str(row['token_id'] or ''),
        str(row['outcome'] or ''),
    )


def resolve_position_prices(rows: list[Any], now_str: str) -> dict[tuple[str, str, str, str], Optional[float]]:
    resolved: dict[tuple[str, str, str, str], Optional[float]] = {}
    fetch_missing = allow_sync_price_fetch_in_api()
    get_price_from_market = None
    if fetch_missing:
        from price_fetcher import get_price_from_market as _get_price_from_market
        get_price_from_market = _get_price_from_market

    for row in rows:
        cache_key = position_price_cache_key(row)
        if cache_key in resolved:
            continue

        current_price = row['current_price']
        if current_price is None and get_price_from_market is not None:
            current_price = get_price_from_market(
                row['symbol'],
                now_str,
                row['market'],
                token_id=row['token_id'],
                outcome=row['outcome'],
            )
        resolved[cache_key] = current_price

    return resolved


def normalize_content_fingerprint(content: str) -> str:
    return ' '.join((content or '').strip().lower().split())


def enforce_content_rate_limit(
    ctx: RouteContext,
    agent_id: int,
    action: str,
    content: str,
    target_key: Optional[str] = None,
) -> None:
    now_ts = time.time()
    state_key = (agent_id, action)
    state = ctx.content_rate_limit_state.setdefault(
        state_key,
        {'timestamps': [], 'last_ts': 0.0, 'fingerprints': {}},
    )

    if action == 'discussion':
        cooldown_seconds = DISCUSSION_COOLDOWN_SECONDS
        window_seconds = DISCUSSION_WINDOW_SECONDS
        window_limit = DISCUSSION_WINDOW_LIMIT
    else:
        cooldown_seconds = REPLY_COOLDOWN_SECONDS
        window_seconds = REPLY_WINDOW_SECONDS
        window_limit = REPLY_WINDOW_LIMIT

    last_ts = float(state.get('last_ts') or 0.0)
    if now_ts - last_ts < cooldown_seconds:
        remaining = int(math.ceil(cooldown_seconds - (now_ts - last_ts)))
        raise HTTPException(status_code=429, detail=f'Too many {action} posts. Try again in {remaining}s.')

    timestamps = [ts for ts in state.get('timestamps', []) if now_ts - ts < window_seconds]
    if len(timestamps) >= window_limit:
        raise HTTPException(status_code=429, detail=f'{action.title()} rate limit reached. Please slow down.')

    fingerprints = state.get('fingerprints', {})
    fingerprint = normalize_content_fingerprint(content)
    duplicate_key = f"{target_key or 'global'}::{fingerprint}"
    last_duplicate_ts = fingerprints.get(duplicate_key)
    if last_duplicate_ts and now_ts - float(last_duplicate_ts) < CONTENT_DUPLICATE_WINDOW_SECONDS:
        raise HTTPException(status_code=429, detail=f'Duplicate {action} content detected. Please wait before reposting.')

    timestamps.append(now_ts)
    fingerprints = {
        key: ts
        for key, ts in fingerprints.items()
        if now_ts - float(ts) < CONTENT_DUPLICATE_WINDOW_SECONDS
    }
    fingerprints[duplicate_key] = now_ts
    ctx.content_rate_limit_state[state_key] = {
        'timestamps': timestamps,
        'last_ts': now_ts,
        'fingerprints': fingerprints,
    }


def is_us_market_open() -> bool:
    et_tz = ZoneInfo('America/New_York')
    now_et = datetime.now(et_tz)
    day = now_et.weekday()
    time_in_minutes = now_et.hour * 60 + now_et.minute
    return day < 5 and 570 <= time_in_minutes < 960


def is_market_open(market: str) -> bool:
    normalized_market = normalize_market(market)
    if normalized_market in ('crypto', 'polymarket'):
        return True
    if normalized_market == 'us-stock':
        return is_us_market_open()
    return True


def validate_executed_at(executed_at: str, market: str) -> tuple[bool, str]:
    try:
        normalized_market = normalize_market(market)
        if executed_at.lower() == 'now':
            if not is_market_open(normalized_market):
                if normalized_market == 'us-stock':
                    et_tz = ZoneInfo('America/New_York')
                    now_et = datetime.now(et_tz)
                    return (
                        False,
                        'US market is closed. '
                        f"Current time (ET): {now_et.strftime('%Y-%m-%d %H:%M:%S')}. "
                        'Trading hours: Mon-Fri 9:30-16:00 ET',
                    )
                return False, f'{normalized_market} is currently closed'
            return True, ''

        executed_at_clean = executed_at.strip()
        is_utc = executed_at_clean.endswith('Z') or '+00:00' in executed_at_clean
        if not is_utc:
            return False, f'executed_at must be in UTC format (ending with Z or +00:00). Got: {executed_at}'

        try:
            dt_utc = datetime.fromisoformat(executed_at_clean.replace('Z', '+00:00')).replace(tzinfo=timezone.utc)
        except ValueError:
            return (
                False,
                f'Invalid datetime format: {executed_at}. '
                'Use ISO 8601 UTC format (e.g., 2026-03-07T14:30:00Z)',
            )

        dt_et = dt_utc.astimezone(ZoneInfo('America/New_York'))
        day = dt_et.weekday()
        time_in_minutes = dt_et.hour * 60 + dt_et.minute

        if normalized_market == 'us-stock':
            is_weekday = day < 5
            is_market_hours = 570 <= time_in_minutes < 960
            if not (is_weekday and is_market_hours):
                day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
                return (
                    False,
                    f"US market is closed on {day_names[day]} at {dt_et.strftime('%H:%M')} ET. "
                    'Trading hours: Mon-Fri 9:30-16:00 ET',
                )

        return True, ''
    except Exception as exc:
        return False, f'Invalid executed_at: {exc}'


def invalidate_agent_signal_caches(ctx: RouteContext) -> None:
    from cache import delete_pattern

    ctx.agent_signals_cache.clear()
    delete_pattern(f'{AGENT_SIGNALS_CACHE_KEY_PREFIX}:*')


def invalidate_signal_list_caches(ctx: RouteContext) -> None:
    from cache import delete_pattern

    ctx.grouped_signals_cache.clear()
    ctx.signal_feed_cache.clear()
    delete_pattern(f'{GROUPED_SIGNALS_CACHE_KEY_PREFIX}:*')
    delete_pattern(f'{SIGNAL_FEED_CACHE_KEY_PREFIX}:*')
    invalidate_agent_signal_caches(ctx)


def invalidate_leaderboard_caches(ctx: RouteContext) -> None:
    from cache import delete_pattern

    ctx.leaderboard_cache.clear()
    delete_pattern(f'{LEADERBOARD_CACHE_KEY_PREFIX}:*')


def invalidate_trending_caches() -> None:
    from cache import delete
    import tasks as task_runtime

    task_runtime.trending_cache.clear()
    delete(TRENDING_CACHE_KEY)


def invalidate_signal_read_caches(ctx: RouteContext, refresh_trending: bool = False) -> None:
    invalidate_signal_list_caches(ctx)
    invalidate_leaderboard_caches(ctx)
    if refresh_trending:
        invalidate_trending_caches()


def invalidate_position_cache(ctx: RouteContext, agent_id: int | None = None) -> None:
    if agent_id is None:
        ctx.positions_cache.clear()
        return
    ctx.positions_cache.pop(agent_id, None)


def get_position_snapshot(cursor: Any, agent_id: int, market: str, symbol: str, token_id: Optional[str]):
    if market == 'polymarket':
        cursor.execute(
            """
            SELECT quantity, entry_price
            FROM positions
            WHERE agent_id = ? AND market = ? AND token_id = ?
            """,
            (agent_id, market, token_id),
        )
    else:
        cursor.execute(
            """
            SELECT quantity, entry_price
            FROM positions
            WHERE agent_id = ? AND symbol = ? AND market = ?
            """,
            (agent_id, symbol, market),
        )
    return cursor.fetchone()


async def push_agent_message(
    ctx: RouteContext,
    agent_id: int,
    message_type: str,
    content: str,
    data: Optional[Dict[str, Any]] = None,
) -> None:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO agent_messages (agent_id, type, content, data)
        VALUES (?, ?, ?, ?)
        """,
        (agent_id, message_type, content, json.dumps(data) if data else None),
    )
    conn.commit()
    conn.close()
    invalidate_agent_message_caches(ctx, agent_id)

    if agent_id in ctx.ws_connections:
        try:
            await ctx.ws_connections[agent_id].send_json({
                'type': message_type,
                'content': content,
                'data': data,
            })
        except Exception:
            pass


async def notify_followers_of_post(
    ctx: RouteContext,
    leader_id: int,
    leader_name: str,
    message_type: str,
    signal_id: int,
    market: str,
    title: Optional[str] = None,
    symbol: Optional[str] = None,
) -> None:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT follower_id
        FROM subscriptions
        WHERE leader_id = ? AND status = 'active'
        """,
        (leader_id,),
    )
    followers = [row['follower_id'] for row in cursor.fetchall() if row['follower_id'] != leader_id]
    conn.close()

    market_label = market or 'market'
    title_part = f'"{title}"' if title else None
    symbol_part = f' ({symbol})' if symbol else ''

    if message_type == 'strategy':
        if title_part:
            content = f'{leader_name} published strategy {title_part} in {market_label}'
        else:
            content = f'{leader_name} published a new strategy in {market_label}'
        notify_type = 'strategy_published'
    else:
        if title_part:
            content = f'{leader_name} started discussion {title_part}{symbol_part}'
        elif symbol:
            content = f'{leader_name} started a discussion on {symbol}'
        else:
            content = f'{leader_name} started a new discussion in {market_label}'
        notify_type = 'discussion_started'

    payload = {
        'signal_id': signal_id,
        'leader_id': leader_id,
        'leader_name': leader_name,
        'message_type': message_type,
        'market': market,
        'title': title,
        'symbol': symbol,
    }

    for follower_id in followers:
        await push_agent_message(ctx, follower_id, notify_type, content, payload)
