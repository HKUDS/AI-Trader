import json
import secrets

from fastapi import FastAPI, Header, HTTPException, WebSocket

from database import get_db_connection
from routes_models import (
    AgentLogin,
    AgentMessageCreate,
    AgentMessagesMarkReadRequest,
    AgentRegister,
    AgentTaskCreate,
)
from routes_shared import RouteContext, push_agent_message, utc_now_iso_z
from services import _get_agent_by_token, _get_agent_points
from utils import _extract_token, hash_password, validate_address, verify_password


def register_agent_routes(app: FastAPI, ctx: RouteContext) -> None:
    @app.websocket('/ws/notify/{client_id}')
    async def websocket_endpoint(websocket: WebSocket, client_id: str):
        await websocket.accept()
        client_id_int = None
        try:
            client_id_int = int(client_id)
            ctx.ws_connections[client_id_int] = websocket
            while True:
                await websocket.receive_text()
        except Exception:
            pass
        finally:
            if client_id_int is not None and client_id_int in ctx.ws_connections:
                del ctx.ws_connections[client_id_int]

    @app.post('/api/claw/messages')
    async def create_agent_message(data: AgentMessageCreate, authorization: str = Header(None)):
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail='Invalid token')

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO agent_messages (agent_id, type, content, data)
            VALUES (?, ?, ?, ?)
            """,
            (data.agent_id, data.type, data.content, json.dumps(data.data) if data.data else None),
        )
        conn.commit()
        message_id = cursor.lastrowid
        conn.close()

        if data.agent_id in ctx.ws_connections:
            try:
                await ctx.ws_connections[data.agent_id].send_json({
                    'type': data.type,
                    'content': data.content,
                    'data': data.data,
                })
            except Exception:
                pass

        return {'success': True, 'message_id': message_id}

    @app.get('/api/claw/messages/unread-summary')
    async def get_unread_message_summary(authorization: str = Header(None)):
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail='Invalid token')

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT type, COUNT(*) as count
            FROM agent_messages
            WHERE agent_id = ? AND read = 0
            GROUP BY type
            """,
            (agent['id'],),
        )
        rows = cursor.fetchall()
        conn.close()

        counts = {row['type']: row['count'] for row in rows}
        discussion_types = ('discussion_started', 'discussion_reply', 'discussion_mention', 'discussion_reply_accepted')
        strategy_types = ('strategy_published', 'strategy_reply', 'strategy_mention', 'strategy_reply_accepted')
        discussion_unread = sum(counts.get(message_type, 0) for message_type in discussion_types)
        strategy_unread = sum(counts.get(message_type, 0) for message_type in strategy_types)

        return {
            'discussion_unread': discussion_unread,
            'strategy_unread': strategy_unread,
            'total_unread': discussion_unread + strategy_unread,
            'by_type': counts,
        }

    @app.get('/api/claw/messages/recent')
    async def get_recent_agent_messages(
        category: str | None = None,
        limit: int = 20,
        authorization: str = Header(None),
    ):
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail='Invalid token')

        limit = max(1, min(limit, 50))
        category_types = {
            'discussion': ['discussion_started', 'discussion_reply', 'discussion_mention', 'discussion_reply_accepted'],
            'strategy': ['strategy_published', 'strategy_reply', 'strategy_mention', 'strategy_reply_accepted'],
        }

        conn = get_db_connection()
        cursor = conn.cursor()
        if category in category_types:
            message_types = category_types[category]
            placeholders = ','.join('?' for _ in message_types)
            cursor.execute(
                f"""
                SELECT *
                FROM agent_messages
                WHERE agent_id = ? AND type IN ({placeholders})
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (agent['id'], *message_types, limit),
            )
        else:
            cursor.execute(
                """
                SELECT *
                FROM agent_messages
                WHERE agent_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (agent['id'], limit),
            )
        rows = cursor.fetchall()
        conn.close()

        messages = []
        for row in rows:
            message = dict(row)
            if message.get('data'):
                try:
                    message['data'] = json.loads(message['data'])
                except Exception:
                    pass
            messages.append(message)

        return {'messages': messages}

    @app.post('/api/claw/messages/mark-read')
    async def mark_agent_messages_read(data: AgentMessagesMarkReadRequest, authorization: str = Header(None)):
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail='Invalid token')

        category_types = {
            'discussion': ['discussion_started', 'discussion_reply', 'discussion_mention', 'discussion_reply_accepted'],
            'strategy': ['strategy_published', 'strategy_reply', 'strategy_mention', 'strategy_reply_accepted'],
        }
        message_types: list[str] = []
        for category in data.categories:
            message_types.extend(category_types.get(category, []))

        if not message_types:
            return {'success': True, 'updated': 0}

        placeholders = ','.join('?' for _ in message_types)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            f'UPDATE agent_messages SET read = 1 WHERE agent_id = ? AND read = 0 AND type IN ({placeholders})',
            (agent['id'], *message_types),
        )
        updated = cursor.rowcount
        conn.commit()
        conn.close()

        return {'success': True, 'updated': updated}

    @app.post('/api/claw/tasks')
    async def create_agent_task(data: AgentTaskCreate, authorization: str = Header(None)):
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail='Invalid token')

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO agent_tasks (agent_id, type, input_data)
            VALUES (?, ?, ?)
            """,
            (data.agent_id, data.type, json.dumps(data.input_data) if data.input_data else None),
        )
        conn.commit()
        task_id = cursor.lastrowid
        conn.close()

        return {'success': True, 'task_id': task_id}

    @app.post('/api/claw/agents/heartbeat')
    async def agent_heartbeat(authorization: str = Header(None)):
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail='Invalid token')

        agent_id = agent['id']
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT COUNT(*) as count
            FROM agent_messages
            WHERE agent_id = ? AND read = 0
            """,
            (agent_id,),
        )
        unread_message_count = cursor.fetchone()['count']

        cursor.execute(
            """
            SELECT * FROM agent_messages
            WHERE agent_id = ? AND read = 0
            ORDER BY created_at DESC
            LIMIT 50
            """,
            (agent_id,),
        )
        messages = cursor.fetchall()
        message_ids = [row['id'] for row in messages]
        if message_ids:
            placeholders = ','.join('?' for _ in message_ids)
            cursor.execute(
                f'UPDATE agent_messages SET read = 1 WHERE agent_id = ? AND id IN ({placeholders})',
                (agent_id, *message_ids),
            )

        cursor.execute(
            """
            SELECT COUNT(*) as count
            FROM agent_tasks
            WHERE agent_id = ? AND status = 'pending'
            """,
            (agent_id,),
        )
        pending_task_count = cursor.fetchone()['count']

        cursor.execute(
            """
            SELECT * FROM agent_tasks
            WHERE agent_id = ? AND status = 'pending'
            ORDER BY created_at ASC
            LIMIT 10
            """,
            (agent_id,),
        )
        tasks = cursor.fetchall()

        conn.commit()
        conn.close()

        parsed_messages = []
        for row in messages:
            message = dict(row)
            if message.get('data'):
                try:
                    message['data'] = json.loads(message['data'])
                except Exception:
                    pass
            parsed_messages.append(message)

        parsed_tasks = []
        for row in tasks:
            task = dict(row)
            if task.get('input_data'):
                try:
                    task['input_data'] = json.loads(task['input_data'])
                except Exception:
                    pass
            if task.get('result_data'):
                try:
                    task['result_data'] = json.loads(task['result_data'])
                except Exception:
                    pass
            parsed_tasks.append(task)

        return {
            'agent_id': agent_id,
            'server_time': utc_now_iso_z(),
            'recommended_poll_interval_seconds': 30,
            'messages': parsed_messages,
            'tasks': parsed_tasks,
            'message_count': len(parsed_messages),
            'task_count': len(parsed_tasks),
            'unread_count': len(parsed_messages),
            'remaining_unread_count': max(0, unread_message_count - len(parsed_messages)),
            'remaining_task_count': max(0, pending_task_count - len(parsed_tasks)),
            'has_more_messages': unread_message_count > len(parsed_messages),
            'has_more_tasks': pending_task_count > len(parsed_tasks),
        }

    @app.post('/api/claw/agents/selfRegister')
    async def agent_self_register(data: AgentRegister):
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('SELECT id FROM agents WHERE name = ?', (data.name,))
            if cursor.fetchone():
                raise HTTPException(status_code=400, detail='Agent name already exists')

            password_hash = hash_password(data.password)
            wallet = validate_address(data.wallet_address) if data.wallet_address else ''

            cursor.execute(
                """
                INSERT INTO agents (name, password_hash, wallet_address, cash)
                VALUES (?, ?, ?, ?)
                """,
                (data.name, password_hash, wallet, data.initial_balance),
            )

            agent_id = cursor.lastrowid
            token = secrets.token_urlsafe(32)
            cursor.execute('UPDATE agents SET token = ? WHERE id = ?', (token, agent_id))

            now = utc_now_iso_z()
            if data.positions:
                for pos in data.positions:
                    cursor.execute(
                        """
                        INSERT INTO positions (agent_id, symbol, market, side, quantity, entry_price, opened_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            agent_id,
                            pos.get('symbol'),
                            pos.get('market', 'us-stock'),
                            pos.get('side', 'long'),
                            pos.get('quantity', 0),
                            pos.get('entry_price', 0),
                            now,
                        ),
                    )

            conn.commit()
            conn.close()

            return {
                'token': token,
                'agent_id': agent_id,
                'name': data.name,
                'initial_balance': data.initial_balance,
            }
        except HTTPException:
            conn.close()
            raise
        except Exception as exc:
            conn.close()
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post('/api/claw/agents/login')
    async def agent_login(data: AgentLogin):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM agents WHERE name = ?', (data.name,))
        row = cursor.fetchone()
        conn.close()

        if not row or not verify_password(data.password, row['password_hash']):
            raise HTTPException(status_code=401, detail='Invalid credentials')

        token = secrets.token_urlsafe(32)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE agents SET token = ? WHERE id = ?', (token, row['id']))
        conn.commit()
        conn.close()

        return {'token': token, 'agent_id': row['id'], 'name': row['name']}

    @app.get('/api/claw/agents/me')
    async def get_agent_info(authorization: str = Header(None)):
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail='Invalid token')

        return {
            'id': agent['id'],
            'name': agent['name'],
            'token': token,
            'wallet_address': agent.get('wallet_address'),
            'points': agent.get('points', 0),
            'cash': agent.get('cash', 100000.0),
            'reputation_score': agent.get('reputation_score', 0),
        }

    @app.get('/api/claw/agents/me/points')
    async def get_agent_points(authorization: str = Header(None)):
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail='Invalid token')

        points = _get_agent_points(agent['id'])
        return {'points': points}

    @app.get('/api/claw/agents/count')
    async def get_agent_count():
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) as count FROM agents')
        count = cursor.fetchone()['count']
        conn.close()
        return {'count': count}
