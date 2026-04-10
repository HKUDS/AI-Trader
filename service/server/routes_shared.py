import json
import math
import os
import re
import time
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

TRENDING_CACHE_KEY = 'trending:top20'
LEADERBOARD_CACHE_KEY_PREFIX = 'leaderboard:profit_history'
GROUPED_SIGNALS_CACHE_KEY_PREFIX = 'signals:grouped'
AGENT_SIGNALS_CACHE_KEY_PREFIX = 'signals:agent'
PRICE_CACHE_KEY_PREFIX = 'price:quote'

MENTION_PATTERN = re.compile(r'@([A-Za-z0-9_\-]{2,64})')


def allow_sync_price_fetch_in_api() -> bool:
    return os.getenv('ALLOW_SYNC_PRICE_FETCH_IN_API', 'false').strip().lower() in {'1', 'true', 'yes', 'on'}


@dataclass
class RouteContext:
    grouped_signals_cache: dict[tuple[str, str, int, int], tuple[float, dict[str, Any]]] = field(default_factory=dict)
    agent_signals_cache: dict[tuple[int, str, int], tuple[float, dict[str, Any]]] = field(default_factory=dict)
    price_api_last_request: dict[int, float] = field(default_factory=dict)
    price_quote_cache: dict[tuple[str, str, str, str], tuple[float, dict[str, Any]]] = field(default_factory=dict)
    leaderboard_cache: dict[tuple[int, int, int, bool], tuple[float, dict[str, Any]]] = field(default_factory=dict)
    content_rate_limit_state: dict[tuple[int, str], dict[str, Any]] = field(default_factory=dict)
    ws_connections: dict[int, WebSocket] = field(default_factory=dict)
    verification_codes: dict[str, dict[str, Any]] = field(default_factory=dict)


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
    if market in ('crypto', 'polymarket'):
        return True
    if market == 'us-stock':
        return is_us_market_open()
    return True


def validate_executed_at(executed_at: str, market: str) -> tuple[bool, str]:
    try:
        if executed_at.lower() == 'now':
            if not is_market_open(market):
                if market == 'us-stock':
                    et_tz = ZoneInfo('America/New_York')
                    now_et = datetime.now(et_tz)
                    return (
                        False,
                        'US market is closed. '
                        f"Current time (ET): {now_et.strftime('%Y-%m-%d %H:%M:%S')}. "
                        'Trading hours: Mon-Fri 9:30-16:00 ET',
                    )
                return False, f'{market} is currently closed'
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

        if market == 'us-stock':
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
    delete_pattern(f'{GROUPED_SIGNALS_CACHE_KEY_PREFIX}:*')
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
