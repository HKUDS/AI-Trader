import math
import time
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import FastAPI, Header, HTTPException
from zoneinfo import ZoneInfo

from cache import get_json, set_json
from config import (
    DISCUSSION_PUBLISH_REWARD,
    REPLY_PUBLISH_REWARD,
    SIGNAL_PUBLISH_REWARD,
)
from database import begin_write_transaction, get_db_connection
from routes_models import DiscussionRequest, FollowRequest, RealtimeSignalRequest, ReplyRequest, StrategyRequest
from routes_shared import (
    ACCEPT_REPLY_REWARD,
    AGENT_SIGNALS_CACHE_KEY_PREFIX,
    AGENT_SIGNALS_CACHE_TTL_SECONDS,
    GROUPED_SIGNALS_CACHE_KEY_PREFIX,
    GROUPED_SIGNALS_CACHE_TTL_SECONDS,
    RouteContext,
    allow_sync_price_fetch_in_api,
    decorate_polymarket_item,
    enforce_content_rate_limit,
    extract_mentions,
    get_position_snapshot,
    invalidate_agent_signal_caches,
    invalidate_signal_read_caches,
    is_market_open,
    notify_followers_of_post,
    push_agent_message,
    utc_now_iso_z,
    validate_executed_at,
)
from services import _add_agent_points, _get_agent_by_token, _reserve_signal_id, _update_position_from_signal
from utils import _extract_token


def register_signal_routes(app: FastAPI, ctx: RouteContext) -> None:
    @app.post('/api/signals/realtime')
    async def push_realtime_signal(data: RealtimeSignalRequest, authorization: str = Header(None)):
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail='Invalid token')

        agent_id = agent['id']
        now = utc_now_iso_z()
        side = data.action
        action_lower = side.lower()
        fetch_price_in_request = allow_sync_price_fetch_in_api()
        polymarket_token_id = None
        polymarket_outcome = None

        if data.market == 'polymarket' and action_lower in ('short', 'cover'):
            raise HTTPException(
                status_code=400,
                detail='Polymarket paper trading does not support short/cover. Use buy/sell of outcome tokens instead.',
            )

        try:
            qty = float(data.quantity)
        except Exception:
            raise HTTPException(status_code=400, detail='Invalid quantity')

        if not math.isfinite(qty) or qty <= 0:
            raise HTTPException(status_code=400, detail='Invalid quantity')
        if qty > 1_000_000:
            raise HTTPException(status_code=400, detail='Quantity too large')

        if data.market == 'polymarket':
            if data.executed_at.lower() != 'now':
                raise HTTPException(status_code=400, detail="Polymarket historical pricing is not supported. Use executed_at='now'.")
            if fetch_price_in_request:
                from price_fetcher import _polymarket_resolve_reference

                contract = _polymarket_resolve_reference(data.symbol, token_id=data.token_id, outcome=data.outcome)
                if not contract:
                    raise HTTPException(
                        status_code=400,
                        detail='Polymarket trades require an explicit token_id or outcome that resolves to a single outcome token.',
                    )
                polymarket_token_id = contract['token_id']
                polymarket_outcome = contract.get('outcome')
            else:
                polymarket_token_id = (data.token_id or '').strip()
                polymarket_outcome = (data.outcome or '').strip() or None
                if not polymarket_token_id:
                    raise HTTPException(
                        status_code=400,
                        detail='Polymarket trades require token_id when sync price fetch is disabled.',
                    )

        get_price_from_market = None
        if fetch_price_in_request:
            from price_fetcher import get_price_from_market as _get_price_from_market

            get_price_from_market = _get_price_from_market

        if data.executed_at.lower() == 'now':
            now_utc = datetime.now(timezone.utc)
            executed_at = now_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
            now_et = now_utc.astimezone(ZoneInfo('America/New_York'))

            if not is_market_open(data.market):
                if data.market == 'us-stock':
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            'US market is closed. '
                            f"Current time (ET): {now_et.strftime('%Y-%m-%d %H:%M:%S')}. "
                            'Trading hours: Mon-Fri 9:30-16:00 ET'
                        ),
                    )
                raise HTTPException(status_code=400, detail=f'{data.market} is currently closed')

            if get_price_from_market is not None:
                actual_price = get_price_from_market(
                    data.symbol,
                    executed_at,
                    data.market,
                    token_id=polymarket_token_id,
                    outcome=polymarket_outcome,
                )
                if not actual_price:
                    raise HTTPException(status_code=400, detail=f'Unable to fetch current price for {data.symbol}')
                price = actual_price
            else:
                price = data.price
        else:
            is_valid, error_msg = validate_executed_at(data.executed_at, data.market)
            if not is_valid:
                raise HTTPException(status_code=400, detail=error_msg)

            executed_at = data.executed_at
            if not executed_at.endswith('Z') and '+00:00' not in executed_at:
                executed_at = executed_at + 'Z'

            if get_price_from_market is not None:
                actual_price = get_price_from_market(
                    data.symbol,
                    executed_at,
                    data.market,
                    token_id=polymarket_token_id,
                    outcome=polymarket_outcome,
                )
                if not actual_price:
                    raise HTTPException(
                        status_code=400,
                        detail=f'Unable to fetch historical price for {data.symbol} at {executed_at}',
                    )
                price = actual_price
            else:
                price = data.price

        try:
            price = float(price)
        except Exception:
            raise HTTPException(status_code=400, detail='Invalid price')

        if not math.isfinite(price) or price <= 0:
            raise HTTPException(status_code=400, detail='Invalid price')
        if price > 10_000_000:
            raise HTTPException(status_code=400, detail='Price too large')

        timestamp = int(datetime.fromisoformat(executed_at.replace('Z', '+00:00')).timestamp())
        trade_value_guard = price * qty
        if not math.isfinite(trade_value_guard) or trade_value_guard > 1_000_000_000:
            raise HTTPException(status_code=400, detail='Trade value too large')

        from fees import TRADE_FEE_RATE

        signal_id = None
        trade_value = price * qty
        fee = trade_value * TRADE_FEE_RATE
        position_entry_price = None

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            begin_write_transaction(cursor)
            signal_id = _reserve_signal_id(cursor)

            if action_lower in ('sell', 'cover'):
                pos = get_position_snapshot(cursor, agent_id, data.market, data.symbol, polymarket_token_id)
                current_qty = float(pos['quantity']) if pos else 0.0
                position_entry_price = float(pos['entry_price']) if pos and pos['entry_price'] is not None else None
                if action_lower == 'sell':
                    if current_qty <= 0:
                        raise HTTPException(status_code=400, detail='No long position to sell')
                    if qty > current_qty + 1e-12:
                        raise HTTPException(status_code=400, detail='Insufficient long position quantity')
                else:
                    if current_qty >= 0:
                        raise HTTPException(status_code=400, detail='No short position to cover')
                    if qty > abs(current_qty) + 1e-12:
                        raise HTTPException(status_code=400, detail='Insufficient short position quantity')

            if action_lower in ['buy', 'short']:
                total_deduction = trade_value + fee
                cursor.execute('SELECT cash FROM agents WHERE id = ?', (agent_id,))
                row = cursor.fetchone()
                current_cash = row['cash'] if row else 0
                if current_cash < total_deduction:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f'Insufficient cash. Required: ${total_deduction:.2f} '
                            f'(trade: ${trade_value:.2f} + fee: ${fee:.2f}), Available: ${current_cash:.2f}'
                        ),
                    )

            cursor.execute(
                """
                INSERT INTO signals
                (signal_id, agent_id, message_type, market, signal_type, symbol, token_id, outcome, side, entry_price, quantity, content, timestamp, created_at, executed_at)
                VALUES (?, ?, 'operation', ?, 'realtime', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal_id,
                    agent_id,
                    data.market,
                    data.symbol,
                    polymarket_token_id,
                    polymarket_outcome,
                    side,
                    price,
                    qty,
                    data.content,
                    timestamp,
                    now,
                    executed_at,
                ),
            )

            _update_position_from_signal(
                agent_id,
                data.symbol,
                data.market,
                side,
                qty,
                price,
                executed_at,
                cursor=cursor,
                token_id=polymarket_token_id,
                outcome=polymarket_outcome,
            )

            if action_lower in ['buy', 'short']:
                cursor.execute('UPDATE agents SET cash = cash - ? WHERE id = ?', (trade_value + fee, agent_id))
            elif action_lower == 'sell':
                cursor.execute('UPDATE agents SET cash = cash + ? WHERE id = ?', (trade_value - fee, agent_id))
            else:
                if position_entry_price is None:
                    raise HTTPException(status_code=400, detail='Short position entry price is missing')
                cover_credit = ((2 * position_entry_price) - price) * qty - fee
                cursor.execute('UPDATE agents SET cash = cash + ? WHERE id = ?', (cover_credit, agent_id))

            conn.commit()
        except HTTPException:
            conn.rollback()
            conn.close()
            raise
        except Exception as exc:
            conn.rollback()
            conn.close()
            raise HTTPException(status_code=500, detail=f'Failed to record trade: {exc}')
        conn.close()

        _add_agent_points(agent_id, SIGNAL_PUBLISH_REWARD, 'publish_signal')

        follower_count = 0
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            begin_write_transaction(cursor)
            cursor.execute(
                """
                SELECT follower_id FROM subscriptions
                WHERE leader_id = ? AND status = 'active'
                """,
                (agent_id,),
            )
            followers = cursor.fetchall()

            for follower in followers:
                follower_id = follower['follower_id']
                try:
                    cursor.execute(f'SAVEPOINT follower_{follower_id}')
                    follower_position = None

                    if action_lower in ['buy', 'short']:
                        follower_fee = trade_value * TRADE_FEE_RATE
                        follower_total = trade_value + follower_fee
                        cursor.execute('SELECT cash FROM agents WHERE id = ?', (follower_id,))
                        row = cursor.fetchone()
                        follower_cash = row['cash'] if row else 0
                        if follower_cash < follower_total:
                            cursor.execute(f'ROLLBACK TO SAVEPOINT follower_{follower_id}')
                            continue
                    elif action_lower in ['sell', 'cover']:
                        follower_position = get_position_snapshot(
                            cursor,
                            follower_id,
                            data.market,
                            data.symbol,
                            polymarket_token_id,
                        )
                        if action_lower == 'cover' and (not follower_position or follower_position['entry_price'] is None):
                            cursor.execute(f'ROLLBACK TO SAVEPOINT follower_{follower_id}')
                            continue

                    _update_position_from_signal(
                        follower_id,
                        data.symbol,
                        data.market,
                        side,
                        qty,
                        price,
                        executed_at,
                        leader_id=agent_id,
                        cursor=cursor,
                        token_id=polymarket_token_id,
                        outcome=polymarket_outcome,
                    )

                    follower_signal_id = _reserve_signal_id(cursor)
                    leader_name = agent['name'] if isinstance(agent, dict) else 'Leader'
                    copy_content = f'[Copied from {leader_name}] {data.content or ""}'
                    cursor.execute(
                        """
                        INSERT INTO signals
                        (signal_id, agent_id, message_type, market, signal_type, symbol, token_id, outcome, side, entry_price, quantity, content, timestamp, created_at, executed_at)
                        VALUES (?, ?, 'operation', ?, 'realtime', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            follower_signal_id,
                            follower_id,
                            data.market,
                            data.symbol,
                            polymarket_token_id,
                            polymarket_outcome,
                            side,
                            price,
                            qty,
                            copy_content,
                            int(datetime.now(timezone.utc).timestamp()),
                            now,
                            executed_at,
                        ),
                    )

                    if action_lower in ['buy', 'short']:
                        follower_fee = trade_value * TRADE_FEE_RATE
                        follower_total = trade_value + follower_fee
                        cursor.execute('UPDATE agents SET cash = cash - ? WHERE id = ?', (follower_total, follower_id))
                    elif action_lower == 'sell':
                        follower_fee = trade_value * TRADE_FEE_RATE
                        follower_net = trade_value - follower_fee
                        cursor.execute('UPDATE agents SET cash = cash + ? WHERE id = ?', (follower_net, follower_id))
                    else:
                        follower_fee = trade_value * TRADE_FEE_RATE
                        follower_entry_price = float(follower_position['entry_price'])
                        follower_net = ((2 * follower_entry_price) - price) * qty - follower_fee
                        cursor.execute('UPDATE agents SET cash = cash + ? WHERE id = ?', (follower_net, follower_id))

                    cursor.execute(f'RELEASE SAVEPOINT follower_{follower_id}')
                    follower_count += 1
                except Exception:
                    try:
                        cursor.execute(f'ROLLBACK TO SAVEPOINT follower_{follower_id}')
                    except Exception:
                        pass

            conn.commit()
            conn.close()
        except Exception:
            try:
                conn.rollback()
                conn.close()
            except Exception:
                pass

        invalidate_signal_read_caches(ctx, refresh_trending=True)

        payload = {
            'success': True,
            'signal_id': signal_id,
            'message_type': 'operation',
            'market': data.market,
            'symbol': data.symbol,
            'price': price,
            'follower_count': follower_count,
            'points_earned': SIGNAL_PUBLISH_REWARD,
            'token_id': polymarket_token_id,
            'outcome': polymarket_outcome,
        }
        if data.market == 'polymarket':
            decorate_polymarket_item(payload, fetch_remote=fetch_price_in_request)
        return payload

    @app.post('/api/signals/strategy')
    async def upload_strategy(data: StrategyRequest, authorization: str = Header(None)):
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail='Invalid token')

        agent_id = agent['id']
        agent_name = agent['name']
        signal_id = _reserve_signal_id()
        now = utc_now_iso_z()

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO signals
            (signal_id, agent_id, message_type, market, signal_type, title, content, symbols, tags, timestamp, created_at)
            VALUES (?, ?, 'strategy', ?, 'strategy', ?, ?, ?, ?, ?, ?)
            """,
            (
                signal_id,
                agent_id,
                data.market,
                data.title,
                data.content,
                data.symbols,
                data.tags,
                int(datetime.now(timezone.utc).timestamp()),
                now,
            ),
        )
        conn.commit()
        conn.close()

        invalidate_signal_read_caches(ctx)
        _add_agent_points(agent_id, SIGNAL_PUBLISH_REWARD, 'publish_strategy')
        await notify_followers_of_post(
            ctx,
            agent_id,
            agent_name,
            'strategy',
            signal_id,
            data.market,
            title=data.title,
        )

        return {'success': True, 'signal_id': signal_id, 'points_earned': SIGNAL_PUBLISH_REWARD}

    @app.post('/api/signals/discussion')
    async def post_discussion(data: DiscussionRequest, authorization: str = Header(None)):
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail='Invalid token')

        enforce_content_rate_limit(
            ctx,
            agent['id'],
            'discussion',
            f'{data.title}\n{data.content}',
            target_key=f"{data.market}:{data.symbol or ''}:{data.title.strip().lower()}",
        )

        agent_id = agent['id']
        agent_name = agent['name']
        signal_id = _reserve_signal_id()
        now = utc_now_iso_z()

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO signals
            (signal_id, agent_id, message_type, market, signal_type, symbol, title, content, timestamp, created_at)
            VALUES (?, ?, 'discussion', ?, 'discussion', ?, ?, ?, ?, ?)
            """,
            (
                signal_id,
                agent_id,
                data.market,
                data.symbol,
                data.title,
                data.content,
                int(datetime.now(timezone.utc).timestamp()),
                now,
            ),
        )
        conn.commit()
        conn.close()

        invalidate_signal_read_caches(ctx)
        _add_agent_points(agent_id, DISCUSSION_PUBLISH_REWARD, 'publish_discussion')
        await notify_followers_of_post(
            ctx,
            agent_id,
            agent_name,
            'discussion',
            signal_id,
            data.market,
            title=data.title,
            symbol=data.symbol,
        )

        return {'success': True, 'signal_id': signal_id, 'points_earned': DISCUSSION_PUBLISH_REWARD}

    @app.get('/api/signals/grouped')
    async def get_signals_grouped(
        message_type: str = None,
        market: str = None,
        limit: int = 20,
        offset: int = 0,
    ):
        cache_key = ((message_type or '').strip(), (market or '').strip(), max(1, limit), max(0, offset))
        now_ts = time.time()
        redis_cache_key = (
            f'{GROUPED_SIGNALS_CACHE_KEY_PREFIX}:'
            f"message_type={(message_type or '').strip() or 'all'}:"
            f"market={(market or '').strip() or 'all'}:"
            f'limit={max(1, limit)}:'
            f'offset={max(0, offset)}'
        )

        cached_payload = get_json(redis_cache_key)
        if isinstance(cached_payload, dict):
            ctx.grouped_signals_cache[cache_key] = (now_ts, cached_payload)
            return cached_payload

        cached = ctx.grouped_signals_cache.get(cache_key)
        if cached and now_ts - cached[0] < GROUPED_SIGNALS_CACHE_TTL_SECONDS:
            return cached[1]

        conn = get_db_connection()
        cursor = conn.cursor()

        conditions = []
        params = []
        if message_type:
            conditions.append('s.message_type = ?')
            params.append(message_type)
        if market:
            conditions.append('s.market = ?')
            params.append(market)

        where_clause = ' AND '.join(conditions) if conditions else '1=1'
        count_query = f"""
            SELECT COUNT(*) AS total FROM (
                SELECT a.id
                FROM agents a
                LEFT JOIN signals s ON s.agent_id = a.id AND {where_clause}
                GROUP BY a.id
                HAVING COUNT(s.id) > 0
            ) grouped_agents
        """
        cursor.execute(count_query, params)
        total_row = cursor.fetchone()
        total = total_row['total'] if total_row else 0

        query = f"""
            SELECT
                a.id as agent_id,
                a.name as agent_name,
                COUNT(s.id) as signal_count,
                COALESCE(SUM(s.pnl), 0) as total_pnl,
                MAX(s.created_at) as last_signal_at,
                (SELECT s2.signal_id FROM signals s2
                 WHERE s2.agent_id = a.id
                 ORDER BY s2.created_at DESC LIMIT 1) as latest_signal_id,
                (SELECT s3.message_type FROM signals s3
                 WHERE s3.agent_id = a.id
                 ORDER BY s3.created_at DESC LIMIT 1) as latest_signal_type
            FROM agents a
            LEFT JOIN signals s ON s.agent_id = a.id AND {where_clause}
            GROUP BY a.id
            HAVING COUNT(s.id) > 0
            ORDER BY last_signal_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        cursor.execute(query, params)
        rows = cursor.fetchall()

        agent_ids = [row['agent_id'] for row in rows]
        positions_by_agent: dict[int, list[dict[str, Any]]] = {}
        if agent_ids:
            placeholders = ','.join('?' for _ in agent_ids)
            cursor.execute(
                f"""
                SELECT agent_id, symbol, market, token_id, outcome, side, quantity, entry_price, current_price
                FROM positions
                WHERE agent_id IN ({placeholders})
                ORDER BY opened_at DESC
                """,
                agent_ids,
            )
            for pos_row in cursor.fetchall():
                positions_by_agent.setdefault(pos_row['agent_id'], []).append(dict(pos_row))

        agents = []
        for row in rows:
            agent_id = row['agent_id']
            position_rows = positions_by_agent.get(agent_id, [])

            position_summary = []
            total_position_pnl = 0
            for pos_row in position_rows:
                current_price = pos_row['current_price']
                pnl = None
                if current_price and pos_row['entry_price']:
                    if pos_row['side'] == 'long':
                        pnl = (current_price - pos_row['entry_price']) * abs(pos_row['quantity'])
                    else:
                        pnl = (pos_row['entry_price'] - current_price) * abs(pos_row['quantity'])
                if pnl:
                    total_position_pnl += pnl
                position_summary.append({
                    'symbol': pos_row['symbol'],
                    'market': pos_row['market'],
                    'token_id': pos_row['token_id'],
                    'outcome': pos_row['outcome'],
                    'side': pos_row['side'],
                    'quantity': pos_row['quantity'],
                    'current_price': current_price,
                    'pnl': pnl,
                })
                if position_summary[-1]['market'] == 'polymarket':
                    decorate_polymarket_item(position_summary[-1], fetch_remote=False)

            agents.append({
                'agent_id': agent_id,
                'agent_name': row['agent_name'],
                'signal_count': row['signal_count'],
                'total_pnl': row['total_pnl'],
                'position_pnl': total_position_pnl,
                'position_count': len(position_rows),
                'positions': position_summary,
                'last_signal_at': row['last_signal_at'],
                'latest_signal_id': row['latest_signal_id'],
                'latest_signal_type': row['latest_signal_type'],
            })

        conn.close()
        payload = {'agents': agents, 'total': total}
        ctx.grouped_signals_cache[cache_key] = (now_ts, payload)
        set_json(redis_cache_key, payload, ttl_seconds=GROUPED_SIGNALS_CACHE_TTL_SECONDS)
        return payload

    @app.get('/api/signals/{signal_id}/replies')
    async def get_signal_replies(signal_id: int):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT r.*, a.name as agent_name
            FROM signal_replies r
            JOIN agents a ON a.id = r.agent_id
            WHERE r.signal_id = ?
            ORDER BY r.created_at ASC
            """,
            (signal_id,),
        )
        rows = cursor.fetchall()
        conn.close()
        return {'replies': [dict(row) for row in rows]}

    @app.get('/api/signals/feed')
    async def get_signal_feed(
        message_type: str = None,
        market: str = None,
        keyword: str = None,
        limit: int = 50,
        offset: int = 0,
        sort: str = 'new',
        authorization: str = Header(None),
    ):
        limit = max(1, min(limit, 100))
        offset = max(0, offset)
        viewer = None
        token = _extract_token(authorization)
        if token:
            viewer = _get_agent_by_token(token)

        conn = get_db_connection()
        cursor = conn.cursor()

        conditions = []
        params = []

        if message_type:
            conditions.append('s.message_type = ?')
            params.append(message_type)
        if market:
            conditions.append('s.market = ?')
            params.append(market)
        if keyword:
            conditions.append('(s.title LIKE ? OR s.content LIKE ?)')
            keyword_pattern = f'%{keyword}%'
            params.extend([keyword_pattern, keyword_pattern])
        if sort == 'following' and viewer:
            conditions.append(
                """
                (
                    s.agent_id = ?
                    OR EXISTS (
                        SELECT 1 FROM subscriptions sub
                        WHERE sub.leader_id = s.agent_id
                          AND sub.follower_id = ?
                          AND sub.status = 'active'
                    )
                )
                """
            )
            params.extend([viewer['id'], viewer['id']])

        where_clause = ' AND '.join(conditions) if conditions else '1=1'
        if sort in ('active', 'following') and viewer:
            order_clause = """
                COALESCE(
                    (SELECT MAX(sr.created_at) FROM signal_replies sr WHERE sr.signal_id = s.signal_id),
                    s.created_at
                ) DESC,
                (SELECT COUNT(*) FROM signal_replies sr WHERE sr.signal_id = s.signal_id) DESC,
                s.created_at DESC
            """
        elif sort == 'active':
            order_clause = """
                COALESCE(
                    (SELECT MAX(sr.created_at) FROM signal_replies sr WHERE sr.signal_id = s.signal_id),
                    s.created_at
                ) DESC,
                (SELECT COUNT(*) FROM signal_replies sr WHERE sr.signal_id = s.signal_id) DESC,
                s.created_at DESC
            """
        else:
            order_clause = 's.created_at DESC'

        count_query = f"""
            SELECT COUNT(*) AS total
            FROM signals s
            JOIN agents a ON a.id = s.agent_id
            WHERE {where_clause}
        """
        cursor.execute(count_query, params)
        total_row = cursor.fetchone()
        total = total_row['total'] if total_row else 0

        query = f"""
            SELECT
                s.*,
                a.name as agent_name,
                (SELECT COUNT(*) FROM signal_replies sr WHERE sr.signal_id = s.signal_id) as reply_count,
                (SELECT MAX(sr.created_at) FROM signal_replies sr WHERE sr.signal_id = s.signal_id) as last_reply_at,
                (SELECT COUNT(DISTINCT sr.agent_id) + 1 FROM signal_replies sr WHERE sr.signal_id = s.signal_id) as participant_count
            FROM signals s
            JOIN agents a ON a.id = s.agent_id
            WHERE {where_clause}
            ORDER BY {order_clause}
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()
        followed_author_ids = set()
        if viewer:
            cursor.execute(
                """
                SELECT leader_id
                FROM subscriptions
                WHERE follower_id = ? AND status = 'active'
                """,
                (viewer['id'],),
            )
            followed_author_ids = {row['leader_id'] for row in cursor.fetchall()}
        conn.close()

        signals = []
        for row in rows:
            signal_dict = dict(row)
            if signal_dict.get('symbols') and isinstance(signal_dict['symbols'], str):
                signal_dict['symbols'] = [s.strip() for s in signal_dict['symbols'].split(',') if s.strip()]
            if signal_dict.get('tags') and isinstance(signal_dict['tags'], str):
                signal_dict['tags'] = [t.strip() for t in signal_dict['tags'].split(',') if t.strip()]
            if signal_dict.get('participant_count') in (None, 0):
                signal_dict['participant_count'] = 1
            if signal_dict.get('market') == 'polymarket':
                decorate_polymarket_item(signal_dict, fetch_remote=False)
            signal_dict['is_following_author'] = signal_dict['agent_id'] in followed_author_ids
            signals.append(signal_dict)

        return {
            'signals': signals,
            'total': total,
            'limit': limit,
            'offset': offset,
            'has_more': offset + len(signals) < total,
        }

    @app.get('/api/signals/following')
    async def get_following(
        limit: int = 500,
        offset: int = 0,
        authorization: str = Header(None),
    ):
        limit = max(1, min(limit, 500))
        offset = max(0, offset)
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail='Invalid token')

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(*) AS total
            FROM subscriptions
            WHERE follower_id = ? AND status = 'active'
            """,
            (agent['id'],),
        )
        total_row = cursor.fetchone()
        total = total_row['total'] if total_row else 0

        cursor.execute(
            """
            SELECT
                s.leader_id,
                a.name as leader_name,
                s.created_at as subscribed_at,
                (SELECT COUNT(*) FROM subscriptions sub WHERE sub.leader_id = s.leader_id AND sub.status = 'active') as follower_count,
                (SELECT COUNT(*) FROM signals sig WHERE sig.agent_id = s.leader_id AND sig.message_type = 'operation' AND sig.created_at >= datetime('now', '-7 day')) as recent_trade_count_7d,
                (SELECT COUNT(*) FROM signals sig WHERE sig.agent_id = s.leader_id AND sig.message_type = 'strategy' AND sig.created_at >= datetime('now', '-7 day')) as recent_strategy_count_7d,
                (SELECT COUNT(*) FROM signals sig WHERE sig.agent_id = s.leader_id AND sig.message_type = 'discussion' AND sig.created_at >= datetime('now', '-7 day')) as recent_discussion_count_7d,
                (SELECT MAX(sig.created_at) FROM signals sig WHERE sig.agent_id = s.leader_id) as recent_activity_at,
                (SELECT sig.signal_id FROM signals sig WHERE sig.agent_id = s.leader_id AND sig.message_type = 'strategy' ORDER BY sig.created_at DESC LIMIT 1) as latest_strategy_signal_id,
                (SELECT sig.title FROM signals sig WHERE sig.agent_id = s.leader_id AND sig.message_type = 'strategy' ORDER BY sig.created_at DESC LIMIT 1) as latest_strategy_title,
                (SELECT sig.signal_id FROM signals sig WHERE sig.agent_id = s.leader_id AND sig.message_type = 'discussion' ORDER BY sig.created_at DESC LIMIT 1) as latest_discussion_signal_id,
                (SELECT sig.title FROM signals sig WHERE sig.agent_id = s.leader_id AND sig.message_type = 'discussion' ORDER BY sig.created_at DESC LIMIT 1) as latest_discussion_title
            FROM subscriptions s
            JOIN agents a ON a.id = s.leader_id
            WHERE s.follower_id = ? AND s.status = 'active'
            ORDER BY COALESCE(
                (SELECT MAX(sig.created_at) FROM signals sig WHERE sig.agent_id = s.leader_id),
                s.created_at
            ) DESC
            LIMIT ? OFFSET ?
            """,
            (agent['id'], limit, offset),
        )
        rows = cursor.fetchall()
        conn.close()

        following = []
        for row in rows:
            following.append({
                'leader_id': row['leader_id'],
                'leader_name': row['leader_name'],
                'subscribed_at': row['subscribed_at'],
                'follower_count': row['follower_count'] or 0,
                'recent_trade_count_7d': row['recent_trade_count_7d'] or 0,
                'recent_strategy_count_7d': row['recent_strategy_count_7d'] or 0,
                'recent_discussion_count_7d': row['recent_discussion_count_7d'] or 0,
                'recent_activity_at': row['recent_activity_at'],
                'latest_strategy_signal_id': row['latest_strategy_signal_id'],
                'latest_strategy_title': row['latest_strategy_title'],
                'latest_discussion_signal_id': row['latest_discussion_signal_id'],
                'latest_discussion_title': row['latest_discussion_title'],
            })

        return {
            'following': following,
            'total': total,
            'limit': limit,
            'offset': offset,
            'has_more': offset + len(following) < total,
        }

    @app.get('/api/signals/subscribers')
    async def get_subscribers(authorization: str = Header(None)):
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail='Invalid token')

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                s.follower_id,
                a.name as follower_name,
                s.created_at as subscribed_at,
                (SELECT COUNT(*) FROM signals sig WHERE sig.agent_id = s.follower_id AND sig.message_type = 'operation' AND sig.created_at >= datetime('now', '-7 day')) as recent_trade_count_7d,
                (SELECT COUNT(*) FROM signals sig WHERE sig.agent_id = s.follower_id AND sig.message_type IN ('strategy', 'discussion') AND sig.created_at >= datetime('now', '-7 day')) as recent_social_count_7d,
                (SELECT MAX(sig.created_at) FROM signals sig WHERE sig.agent_id = s.follower_id) as recent_activity_at
            FROM subscriptions s
            JOIN agents a ON a.id = s.follower_id
            WHERE s.leader_id = ? AND s.status = 'active'
            ORDER BY COALESCE(
                (SELECT MAX(sig.created_at) FROM signals sig WHERE sig.agent_id = s.follower_id),
                s.created_at
            ) DESC
            """,
            (agent['id'],),
        )
        rows = cursor.fetchall()
        conn.close()

        subscribers = []
        for row in rows:
            subscribers.append({
                'follower_id': row['follower_id'],
                'follower_name': row['follower_name'],
                'subscribed_at': row['subscribed_at'],
                'recent_trade_count_7d': row['recent_trade_count_7d'] or 0,
                'recent_social_count_7d': row['recent_social_count_7d'] or 0,
                'recent_activity_at': row['recent_activity_at'],
            })

        return {'subscribers': subscribers}

    @app.get('/api/signals/{agent_id}')
    async def get_agent_signals(agent_id: int, message_type: str = None, limit: int = 50):
        cache_key = (agent_id, (message_type or '').strip(), max(1, limit))
        now_ts = time.time()
        redis_cache_key = (
            f'{AGENT_SIGNALS_CACHE_KEY_PREFIX}:'
            f'agent_id={agent_id}:'
            f"message_type={(message_type or '').strip() or 'all'}:"
            f'limit={max(1, limit)}'
        )

        cached_payload = get_json(redis_cache_key)
        if isinstance(cached_payload, dict):
            ctx.agent_signals_cache[cache_key] = (now_ts, cached_payload)
            return cached_payload

        cached = ctx.agent_signals_cache.get(cache_key)
        if cached and now_ts - cached[0] < AGENT_SIGNALS_CACHE_TTL_SECONDS:
            return cached[1]

        conn = get_db_connection()
        cursor = conn.cursor()

        query = 'SELECT * FROM signals WHERE agent_id = ?'
        params = [agent_id]
        if message_type:
            query += ' AND message_type = ?'
            params.append(message_type)
        query += ' ORDER BY created_at DESC LIMIT ?'
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        signals = []
        for row in rows:
            signal_dict = dict(row)
            if signal_dict.get('symbols') and isinstance(signal_dict['symbols'], str):
                signal_dict['symbols'] = [s.strip() for s in signal_dict['symbols'].split(',') if s.strip()]
            if signal_dict.get('tags') and isinstance(signal_dict['tags'], str):
                signal_dict['tags'] = [t.strip() for t in signal_dict['tags'].split(',') if t.strip()]
            if signal_dict.get('market') == 'polymarket':
                decorate_polymarket_item(signal_dict, fetch_remote=False)
            signals.append(signal_dict)

        payload = {'signals': signals}
        ctx.agent_signals_cache[cache_key] = (now_ts, payload)
        set_json(redis_cache_key, payload, ttl_seconds=AGENT_SIGNALS_CACHE_TTL_SECONDS)
        return payload

    @app.post('/api/signals/reply')
    async def reply_to_signal(data: ReplyRequest, authorization: str = Header(None)):
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail='Invalid token')

        enforce_content_rate_limit(ctx, agent['id'], 'reply', data.content, target_key=f'signal:{data.signal_id}')

        agent_id = agent['id']
        agent_name = agent['name']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT s.signal_id, s.agent_id, s.message_type, s.market, s.symbol, s.title
            FROM signals s
            WHERE s.signal_id = ?
            """,
            (data.signal_id,),
        )
        signal_row = cursor.fetchone()
        if not signal_row:
            conn.close()
            raise HTTPException(status_code=404, detail='Signal not found')

        cursor.execute(
            """
            INSERT INTO signal_replies (signal_id, agent_id, content)
            VALUES (?, ?, ?)
            """,
            (data.signal_id, agent_id, data.content),
        )
        conn.commit()
        conn.close()

        _add_agent_points(agent_id, REPLY_PUBLISH_REWARD, 'publish_reply')

        original_author_id = signal_row['agent_id']
        title = signal_row['title'] or signal_row['symbol'] or f"signal {signal_row['signal_id']}"
        reply_message_type = 'strategy_reply' if signal_row['message_type'] == 'strategy' else 'discussion_reply'
        mention_message_type = 'strategy_mention' if signal_row['message_type'] == 'strategy' else 'discussion_mention'
        reply_target_label = f'"{title}"' if signal_row['title'] else title

        if original_author_id != agent_id:
            await push_agent_message(
                ctx,
                original_author_id,
                reply_message_type,
                f"{agent_name} replied to your {signal_row['message_type']} {reply_target_label}",
                {
                    'signal_id': signal_row['signal_id'],
                    'reply_author_id': agent_id,
                    'reply_author_name': agent_name,
                    'parent_message_type': signal_row['message_type'],
                    'market': signal_row['market'],
                    'symbol': signal_row['symbol'],
                    'title': title,
                },
            )

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT DISTINCT agent_id
            FROM signal_replies
            WHERE signal_id = ?
            """,
            (data.signal_id,),
        )
        participant_ids = {
            row['agent_id'] for row in cursor.fetchall() if row['agent_id'] not in (agent_id, original_author_id)
        }
        conn.close()

        for participant_id in participant_ids:
            await push_agent_message(
                ctx,
                participant_id,
                reply_message_type,
                f'{agent_name} added a new reply in {reply_target_label}',
                {
                    'signal_id': signal_row['signal_id'],
                    'reply_author_id': agent_id,
                    'reply_author_name': agent_name,
                    'parent_message_type': signal_row['message_type'],
                    'market': signal_row['market'],
                    'symbol': signal_row['symbol'],
                    'title': title,
                },
            )

        mentioned_names = extract_mentions(data.content)
        if mentioned_names:
            conn = get_db_connection()
            cursor = conn.cursor()
            placeholders = ','.join('?' for _ in mentioned_names)
            cursor.execute(
                f'SELECT id, name FROM agents WHERE LOWER(name) IN ({placeholders})',
                [name.lower() for name in mentioned_names],
            )
            mentioned_agents = cursor.fetchall()
            conn.close()
            excluded_ids = {agent_id, original_author_id, *participant_ids}
            for mentioned_agent in mentioned_agents:
                if mentioned_agent['id'] in excluded_ids:
                    continue
                await push_agent_message(
                    ctx,
                    mentioned_agent['id'],
                    mention_message_type,
                    f'{agent_name} mentioned you in {reply_target_label}',
                    {
                        'signal_id': signal_row['signal_id'],
                        'reply_author_id': agent_id,
                        'reply_author_name': agent_name,
                        'parent_message_type': signal_row['message_type'],
                        'market': signal_row['market'],
                        'symbol': signal_row['symbol'],
                        'title': title,
                    },
                )

        return {'success': True, 'points_earned': REPLY_PUBLISH_REWARD}

    @app.post('/api/signals/{signal_id}/replies/{reply_id}/accept')
    async def accept_signal_reply(signal_id: int, reply_id: int, authorization: str = Header(None)):
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail='Invalid token')

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT s.signal_id, s.agent_id, s.message_type, s.symbol, s.title, r.agent_id AS reply_author_id, r.accepted
            FROM signals s
            JOIN signal_replies r ON r.id = ?
            WHERE s.signal_id = ? AND r.signal_id = s.signal_id
            """,
            (reply_id, signal_id),
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail='Reply not found')
        if row['agent_id'] != agent['id']:
            conn.close()
            raise HTTPException(status_code=403, detail='Only the original author can accept a reply')

        cursor.execute('UPDATE signal_replies SET accepted = 0 WHERE signal_id = ?', (signal_id,))
        cursor.execute('UPDATE signal_replies SET accepted = 1 WHERE id = ?', (reply_id,))
        cursor.execute('UPDATE signals SET accepted_reply_id = ? WHERE signal_id = ?', (reply_id, signal_id))
        conn.commit()
        conn.close()

        invalidate_agent_signal_caches(ctx)

        if row['reply_author_id'] != agent['id']:
            _add_agent_points(row['reply_author_id'], ACCEPT_REPLY_REWARD, 'reply_accepted')
            title = row['title'] or row['symbol'] or f'signal {signal_id}'
            await push_agent_message(
                ctx,
                row['reply_author_id'],
                'strategy_reply_accepted' if row['message_type'] == 'strategy' else 'discussion_reply_accepted',
                f"{agent['name']} accepted your reply on \"{title}\"",
                {
                    'signal_id': signal_id,
                    'reply_id': reply_id,
                    'reply_author_id': row['reply_author_id'],
                    'accepted_by_id': agent['id'],
                    'accepted_by_name': agent['name'],
                    'title': title,
                    'parent_message_type': row['message_type'],
                },
            )

        return {'success': True, 'reply_id': reply_id, 'points_earned': ACCEPT_REPLY_REWARD}
