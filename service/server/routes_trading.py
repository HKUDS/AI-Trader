import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import tasks as task_runtime
from fastapi import FastAPI, Header, HTTPException

from cache import get_json, set_json
from database import get_db_connection
from routes_models import FollowRequest
from routes_shared import (
    LEADERBOARD_CACHE_KEY_PREFIX,
    LEADERBOARD_CACHE_TTL_SECONDS,
    PRICE_CACHE_KEY_PREFIX,
    PRICE_QUOTE_CACHE_TTL_SECONDS,
    RouteContext,
    TRENDING_CACHE_KEY,
    allow_sync_price_fetch_in_api,
    check_price_api_rate_limit,
    clamp_profit_for_display,
    decorate_polymarket_item,
    position_price_cache_key,
    push_agent_message,
    resolve_position_prices,
    utc_now_iso_z,
)
from services import _get_agent_by_token
from utils import _extract_token


def register_trading_routes(app: FastAPI, ctx: RouteContext) -> None:
    @app.get('/api/profit/history')
    async def get_profit_history(
        limit: int = 10,
        days: int = 30,
        offset: int = 0,
        include_history: bool = True,
    ):
        days = max(1, min(days, 365))
        limit = max(1, min(limit, 50))
        offset = max(0, offset)

        cache_key = (limit, days, offset, include_history)
        now_ts = time.time()
        redis_cache_key = (
            f'{LEADERBOARD_CACHE_KEY_PREFIX}:'
            f'limit={limit}:days={days}:offset={offset}:history={int(include_history)}'
        )

        cached_payload = get_json(redis_cache_key)
        if isinstance(cached_payload, dict):
            ctx.leaderboard_cache[cache_key] = (now_ts, cached_payload)
            return cached_payload

        cached = ctx.leaderboard_cache.get(cache_key)
        if cached and now_ts - cached[0] < LEADERBOARD_CACHE_TTL_SECONDS:
            return cached[1]

        conn = get_db_connection()
        cursor = conn.cursor()

        cutoff_dt = datetime.now(timezone.utc) - timedelta(days=days)
        cutoff = cutoff_dt.isoformat().replace('+00:00', 'Z')
        live_snapshot_recorded_at = utc_now_iso_z()

        cursor.execute(
            """
            SELECT COUNT(*) AS total
            FROM agents
            """
        )
        total_row = cursor.fetchone()
        total = total_row['total'] if total_row else 0

        cursor.execute(
            """
            SELECT
                a.id AS agent_id,
                a.name,
                (
                    COALESCE(a.cash, 0) +
                    COALESCE(
                        SUM(
                            CASE
                                WHEN p.current_price IS NULL THEN p.entry_price * ABS(p.quantity)
                                WHEN p.side = 'long' THEN p.current_price * ABS(p.quantity)
                                ELSE (2 * p.entry_price - p.current_price) * ABS(p.quantity)
                            END
                        ),
                        0
                    ) -
                    (100000.0 + COALESCE(a.deposited, 0))
                ) AS profit,
                (
                    SELECT MAX(ph.recorded_at)
                    FROM profit_history ph
                    WHERE ph.agent_id = a.id AND ph.recorded_at >= ?
                ) AS recorded_at
            FROM agents a
            LEFT JOIN positions p ON p.agent_id = a.id
            GROUP BY a.id, a.name, a.cash, a.deposited
            ORDER BY profit DESC
            LIMIT ? OFFSET ?
            """,
            (cutoff, limit, offset),
        )
        top_agents = [
            {
                'agent_id': row['agent_id'],
                'name': row['name'],
                'profit': clamp_profit_for_display(row['profit']),
                'recorded_at': row['recorded_at'] or live_snapshot_recorded_at,
            }
            for row in cursor.fetchall()
        ]

        if not top_agents:
            conn.close()
            result = {
                'top_agents': [],
                'total': total,
                'limit': limit,
                'offset': offset,
                'has_more': False,
            }
            ctx.leaderboard_cache[cache_key] = (now_ts, result)
            set_json(redis_cache_key, result, ttl_seconds=LEADERBOARD_CACHE_TTL_SECONDS)
            return result

        agent_ids = [agent['agent_id'] for agent in top_agents]
        placeholders = ','.join('?' for _ in agent_ids)

        cursor.execute(
            f"""
            SELECT agent_id, COUNT(*) as count
            FROM signals
            WHERE message_type = 'operation' AND agent_id IN ({placeholders})
            GROUP BY agent_id
            """,
            agent_ids,
        )
        trade_counts = {row['agent_id']: row['count'] for row in cursor.fetchall()}

        result = []
        for agent in top_agents:
            history_points = []
            if include_history:
                cursor.execute(
                    """
                    SELECT profit, recorded_at
                    FROM (
                        SELECT profit, recorded_at
                        FROM profit_history
                        WHERE agent_id = ? AND recorded_at >= ?
                        ORDER BY recorded_at DESC
                        LIMIT 2000
                    ) recent_history
                    ORDER BY recorded_at ASC
                    """,
                    (agent['agent_id'], cutoff),
                )
                history = cursor.fetchall()
                history_points = [
                    {'profit': clamp_profit_for_display(h['profit']), 'recorded_at': h['recorded_at']}
                    for h in history
                ]

            if include_history and (not history_points or history_points[-1]['recorded_at'] != live_snapshot_recorded_at):
                history_points.append({
                    'profit': clamp_profit_for_display(agent['profit']),
                    'recorded_at': live_snapshot_recorded_at,
                })

            result.append({
                'agent_id': agent['agent_id'],
                'name': agent['name'],
                'total_profit': clamp_profit_for_display(agent['profit']),
                'current_profit': clamp_profit_for_display(agent['profit']),
                'trade_count': trade_counts.get(agent['agent_id'], 0),
                'recent_strategy_count_7d': 0,
                'recent_discussion_count_7d': 0,
                'recent_activity_at': agent['recorded_at'],
                'latest_strategy_signal_id': None,
                'latest_strategy_title': None,
                'latest_discussion_signal_id': None,
                'latest_discussion_title': None,
                'history': history_points,
            })

        cursor.execute(
            f"""
            SELECT agent_id, message_type, COUNT(*) as count, MAX(created_at) as last_created_at
            FROM signals
            WHERE agent_id IN ({placeholders})
              AND message_type IN ('strategy', 'discussion')
              AND created_at >= datetime('now', '-7 day')
            GROUP BY agent_id, message_type
            """,
            agent_ids,
        )
        for row in cursor.fetchall():
            for item in result:
                if item['agent_id'] != row['agent_id']:
                    continue
                if row['message_type'] == 'strategy':
                    item['recent_strategy_count_7d'] = row['count']
                elif row['message_type'] == 'discussion':
                    item['recent_discussion_count_7d'] = row['count']
                if row['last_created_at'] and row['last_created_at'] > (item['recent_activity_at'] or ''):
                    item['recent_activity_at'] = row['last_created_at']
                break

        cursor.execute(
            f"""
            SELECT agent_id, message_type, signal_id, title, created_at
            FROM signals
            WHERE agent_id IN ({placeholders})
              AND message_type IN ('strategy', 'discussion')
            ORDER BY created_at DESC
            """,
            agent_ids,
        )
        seen_latest = set()
        for row in cursor.fetchall():
            key = (row['agent_id'], row['message_type'])
            if key in seen_latest:
                continue
            seen_latest.add(key)
            for item in result:
                if item['agent_id'] != row['agent_id']:
                    continue
                if row['message_type'] == 'strategy':
                    item['latest_strategy_signal_id'] = row['signal_id']
                    item['latest_strategy_title'] = row['title']
                else:
                    item['latest_discussion_signal_id'] = row['signal_id']
                    item['latest_discussion_title'] = row['title']
                if row['created_at'] and row['created_at'] > (item['recent_activity_at'] or ''):
                    item['recent_activity_at'] = row['created_at']
                break

        conn.close()
        payload = {
            'top_agents': result,
            'total': total,
            'limit': limit,
            'offset': offset,
            'has_more': offset + len(result) < total,
        }
        ctx.leaderboard_cache[cache_key] = (now_ts, payload)
        set_json(redis_cache_key, payload, ttl_seconds=LEADERBOARD_CACHE_TTL_SECONDS)
        return payload

    @app.get('/api/leaderboard/position-pnl')
    async def get_leaderboard_position_pnl(limit: int = 10):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id, name FROM agents')
        agents = cursor.fetchall()

        result = []
        for agent in agents:
            agent_id = agent['id']
            cursor.execute(
                """
                SELECT symbol, market, token_id, outcome, side, quantity, entry_price, current_price
                FROM positions WHERE agent_id = ?
                """,
                (agent_id,),
            )
            positions = cursor.fetchall()

            total_position_pnl = 0
            for pos in positions:
                current_price = pos['current_price']
                if current_price and pos['entry_price']:
                    if pos['side'] == 'long':
                        pnl = (current_price - pos['entry_price']) * abs(pos['quantity'])
                    else:
                        pnl = (pos['entry_price'] - current_price) * abs(pos['quantity'])
                    total_position_pnl += pnl

            cursor.execute(
                """
                SELECT COUNT(*) as count FROM signals
                WHERE agent_id = ? AND message_type = 'operation'
                """,
                (agent_id,),
            )
            trade_count = cursor.fetchone()['count']

            result.append({
                'agent_id': agent_id,
                'name': agent['name'],
                'position_pnl': total_position_pnl,
                'trade_count': trade_count,
                'position_count': len(positions),
            })

        conn.close()
        return {'top_agents': sorted(result, key=lambda item: item['position_pnl'], reverse=True)[:limit]}

    @app.get('/api/trending')
    async def get_trending_symbols(limit: int = 10):
        cached = get_json(TRENDING_CACHE_KEY)
        if isinstance(cached, list):
            return {'trending': cached[: max(1, limit)]}

        if task_runtime.trending_cache:
            return {'trending': task_runtime.trending_cache[: max(1, limit)]}

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT symbol, market, token_id, outcome, COUNT(DISTINCT agent_id) as holder_count
            FROM positions
            GROUP BY symbol, market, token_id, outcome
            ORDER BY holder_count DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()

        result = []
        for row in rows:
            cursor.execute(
                """
                SELECT current_price FROM positions
                WHERE symbol = ? AND market = ? AND COALESCE(token_id, '') = COALESCE(?, '')
                LIMIT 1
                """,
                (row['symbol'], row['market'], row['token_id']),
            )
            price_row = cursor.fetchone()
            result.append({
                'symbol': row['symbol'],
                'market': row['market'],
                'token_id': row['token_id'],
                'outcome': row['outcome'],
                'holder_count': row['holder_count'],
                'current_price': price_row['current_price'] if price_row else None,
            })

        conn.close()
        set_json(TRENDING_CACHE_KEY, result, ttl_seconds=300)
        return {'trending': result}

    @app.get('/api/price')
    async def get_price(
        symbol: str,
        market: str = 'us-stock',
        token_id: Optional[str] = None,
        outcome: Optional[str] = None,
        authorization: str = Header(None),
    ):
        token = _extract_token(authorization)
        if not token:
            raise HTTPException(status_code=401, detail='Invalid token')

        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail='Invalid token')

        if not check_price_api_rate_limit(ctx, agent['id']):
            raise HTTPException(status_code=429, detail='Rate limit exceeded. Please wait 1 second between requests.')

        now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        normalized_symbol = symbol.upper() if market == 'us-stock' else symbol
        cache_key = (
            normalized_symbol,
            market,
            (token_id or '').strip(),
            (outcome or '').strip(),
        )
        redis_cache_key = (
            f'{PRICE_CACHE_KEY_PREFIX}:'
            f'symbol={normalized_symbol}:'
            f'market={market}:'
            f"token_id={(token_id or '').strip() or 'none'}:"
            f"outcome={(outcome or '').strip() or 'none'}"
        )

        cached_payload = get_json(redis_cache_key)
        if isinstance(cached_payload, dict):
            ctx.price_quote_cache[cache_key] = (time.time(), cached_payload)
            return cached_payload

        cached = ctx.price_quote_cache.get(cache_key)
        now_ts = time.time()
        if cached and now_ts - cached[0] < PRICE_QUOTE_CACHE_TTL_SECONDS:
            return cached[1]

        price = None
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT current_price
                FROM positions
                WHERE symbol = ? AND market = ? AND COALESCE(token_id, '') = COALESCE(?, '')
                  AND current_price IS NOT NULL
                ORDER BY opened_at DESC
                LIMIT 1
                """,
                (normalized_symbol, market, token_id),
            )
            row = cursor.fetchone()
            if row:
                price = row['current_price']
        finally:
            conn.close()

        if price is None and allow_sync_price_fetch_in_api():
            from price_fetcher import get_price_from_market

            price = get_price_from_market(normalized_symbol, now, market, token_id=token_id, outcome=outcome)
        if price is None:
            raise HTTPException(status_code=404, detail='Price not available')

        payload = {'symbol': normalized_symbol, 'market': market, 'token_id': token_id, 'outcome': outcome, 'price': price}
        if market == 'polymarket':
            decorate_polymarket_item(payload, fetch_remote=allow_sync_price_fetch_in_api())
        ctx.price_quote_cache[cache_key] = (now_ts, payload)
        set_json(redis_cache_key, payload, ttl_seconds=PRICE_QUOTE_CACHE_TTL_SECONDS)
        return payload

    @app.get('/api/positions')
    async def get_my_positions(authorization: str = Header(None)):
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail='Invalid token')

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT p.*, a.name as leader_name
            FROM positions p
            LEFT JOIN agents a ON a.id = p.leader_id
            WHERE p.agent_id = ?
            ORDER BY p.opened_at DESC
            """,
            (agent['id'],),
        )
        rows = cursor.fetchall()
        conn.close()

        positions = []
        now_str = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        resolved_prices = resolve_position_prices(rows, now_str)

        for row in rows:
            current_price = resolved_prices.get(position_price_cache_key(row))
            pnl = None
            if current_price and row['entry_price']:
                if row['side'] == 'long':
                    pnl = (current_price - row['entry_price']) * abs(row['quantity'])
                else:
                    pnl = (row['entry_price'] - current_price) * abs(row['quantity'])

            source = 'self' if row['leader_id'] is None else f"copied:{row['leader_id']}"
            positions.append({
                'id': row['id'],
                'symbol': row['symbol'],
                'market': row['market'],
                'token_id': row['token_id'],
                'outcome': row['outcome'],
                'side': row['side'],
                'quantity': row['quantity'],
                'entry_price': row['entry_price'],
                'current_price': current_price,
                'pnl': pnl,
                'source': source,
                'opened_at': row['opened_at'],
            })
            if positions[-1]['market'] == 'polymarket':
                decorate_polymarket_item(positions[-1], fetch_remote=False)

        return {'positions': positions, 'cash': agent.get('cash', 100000.0)}

    @app.get('/api/agents/{agent_id}/positions')
    async def get_agent_positions(agent_id: int):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT name, cash FROM agents WHERE id = ?', (agent_id,))
        agent_row = cursor.fetchone()
        agent_name = agent_row['name'] if agent_row else 'Unknown'
        agent_cash = agent_row['cash'] if agent_row else 0

        cursor.execute(
            """
            SELECT symbol, market, token_id, outcome, side, quantity, entry_price, current_price
            FROM positions
            WHERE agent_id = ?
            ORDER BY opened_at DESC
            """,
            (agent_id,),
        )
        rows = cursor.fetchall()
        conn.close()

        positions = []
        total_pnl = 0
        now_str = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        resolved_prices = resolve_position_prices(rows, now_str)

        for row in rows:
            current_price = resolved_prices.get(position_price_cache_key(row))
            pnl = None
            if current_price and row['entry_price']:
                if row['side'] == 'long':
                    pnl = (current_price - row['entry_price']) * abs(row['quantity'])
                else:
                    pnl = (row['entry_price'] - current_price) * abs(row['quantity'])
            if pnl:
                total_pnl += pnl

            positions.append({
                'symbol': row['symbol'],
                'market': row['market'],
                'token_id': row['token_id'],
                'outcome': row['outcome'],
                'side': row['side'],
                'quantity': row['quantity'],
                'entry_price': row['entry_price'],
                'current_price': current_price,
                'pnl': pnl,
            })
            if positions[-1]['market'] == 'polymarket':
                decorate_polymarket_item(positions[-1], fetch_remote=False)

        return {
            'positions': positions,
            'total_pnl': total_pnl,
            'position_count': len(positions),
            'agent_name': agent_name,
            'cash': agent_cash,
        }

    @app.get('/api/agents/{agent_id}/summary')
    async def get_agent_summary(agent_id: int):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                a.id,
                a.name,
                a.cash,
                (SELECT MAX(created_at) FROM signals WHERE agent_id = a.id) AS recent_activity_at,
                (SELECT COUNT(*) FROM positions WHERE agent_id = a.id) AS position_count
            FROM agents a
            WHERE a.id = ?
            """,
            (agent_id,),
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            raise HTTPException(status_code=404, detail='Agent not found')

        return {
            'agent_id': row['id'],
            'agent_name': row['name'],
            'cash': row['cash'],
            'position_count': row['position_count'] or 0,
            'recent_activity_at': row['recent_activity_at'],
        }

    @app.post('/api/signals/follow')
    async def follow_provider(data: FollowRequest, authorization: str = Header(None)):
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail='Invalid token')

        follower_id = agent['id']
        leader_id = data.leader_id
        if follower_id == leader_id:
            raise HTTPException(status_code=400, detail='Cannot follow yourself')

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id FROM subscriptions
            WHERE leader_id = ? AND follower_id = ? AND status = 'active'
            """,
            (leader_id, follower_id),
        )
        if cursor.fetchone():
            conn.close()
            return {'message': 'Already following'}

        cursor.execute(
            """
            INSERT INTO subscriptions (leader_id, follower_id, status)
            VALUES (?, ?, 'active')
            """,
            (leader_id, follower_id),
        )
        conn.commit()
        conn.close()

        await push_agent_message(
            ctx,
            leader_id,
            'new_follower',
            f"{agent['name']} started following you",
            {
                'leader_id': leader_id,
                'follower_id': follower_id,
                'follower_name': agent['name'],
            },
        )
        return {'success': True, 'message': 'Following'}

    @app.post('/api/signals/unfollow')
    async def unfollow_provider(data: FollowRequest, authorization: str = Header(None)):
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail='Invalid token')

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE subscriptions SET status = 'inactive'
            WHERE leader_id = ? AND follower_id = ?
            """,
            (data.leader_id, agent['id']),
        )
        conn.commit()
        conn.close()
        return {'success': True}
