import json
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Header, HTTPException, WebSocket

from database import get_db_connection
from experiment_events import record_event
from experiments import variant_for_agent
from routes_models import (
    AgentTokenRecoveryConfirm,
    AgentTokenRecoveryRequest,
    AgentLogin,
    AgentMessageCreate,
    AgentMessagesMarkReadRequest,
    AgentPasswordResetConfirm,
    AgentPasswordResetRequest,
    AgentRegister,
    AgentTaskCreate,
)
from routes_shared import RouteContext, push_agent_message, utc_now_iso_z
from services import (
    _get_agent_by_id,
    _get_agent_by_name,
    _get_agent_by_token,
    _get_agent_points,
    _get_or_issue_agent_token,
    _issue_agent_token,
)
from utils import (
    _extract_token,
    build_agent_token_recovery_challenge,
    build_agent_password_reset_challenge,
    hash_password,
    recover_signed_address,
    validate_address,
    verify_password,
)


DISCUSSION_NOTIFICATION_TYPES = (
    'discussion_started',
    'discussion_reply',
    'discussion_mention',
    'discussion_reply_accepted',
)
STRATEGY_NOTIFICATION_TYPES = (
    'strategy_published',
    'strategy_reply',
    'strategy_mention',
    'strategy_reply_accepted',
)
EXPERIMENT_NOTIFICATION_TYPES = (
    'experiment_announcement',
    'experiment_assignment',
    'experiment_reminder',
    'experiment_rule_update',
    'experiment_result_update',
    'challenge_invite',
    'team_mission_invite',
)


def register_agent_routes(app: FastAPI, ctx: RouteContext) -> None:
    def _resolve_agent_recovery_target(agent_id: int | None, name: str | None) -> dict:
        normalized_name = (name or '').strip()
        if agent_id is None and not normalized_name:
            raise HTTPException(status_code=400, detail='agent_id or name is required')

        agent = _get_agent_by_id(agent_id) if agent_id is not None else None
        if agent_id is not None and not agent:
            raise HTTPException(status_code=404, detail='Agent not found')

        if normalized_name:
            named_agent = _get_agent_by_name(normalized_name)
            if not named_agent:
                raise HTTPException(status_code=404, detail='Agent not found')
            if agent and named_agent['id'] != agent['id']:
                raise HTTPException(status_code=400, detail='agent_id and name refer to different agents')
            agent = named_agent

        if not agent:
            raise HTTPException(status_code=404, detail='Agent not found')

        wallet_address = validate_address(agent.get('wallet_address') or '')
        if not wallet_address:
            raise HTTPException(status_code=400, detail='Agent has no wallet-based recovery configured')

        agent['wallet_address'] = wallet_address
        return agent

    @app.websocket('/ws/notify/{client_id}')
    async def websocket_endpoint(websocket: WebSocket, client_id: str):
        client_id_int = None
        try:
            client_id_int = int(client_id)
            token = websocket.query_params.get('token')
            agent = _get_agent_by_token(token)
            if not agent or int(agent['id']) != client_id_int:
                await websocket.close(code=1008)
                return

            await websocket.accept()
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
        discussion_unread = sum(counts.get(message_type, 0) for message_type in DISCUSSION_NOTIFICATION_TYPES)
        strategy_unread = sum(counts.get(message_type, 0) for message_type in STRATEGY_NOTIFICATION_TYPES)
        experiment_unread = sum(counts.get(message_type, 0) for message_type in EXPERIMENT_NOTIFICATION_TYPES)

        return {
            'discussion_unread': discussion_unread,
            'strategy_unread': strategy_unread,
            'experiment_unread': experiment_unread,
            'total_unread': discussion_unread + strategy_unread + experiment_unread,
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
            'discussion': list(DISCUSSION_NOTIFICATION_TYPES),
            'strategy': list(STRATEGY_NOTIFICATION_TYPES),
            'experiment': list(EXPERIMENT_NOTIFICATION_TYPES),
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
            'discussion': list(DISCUSSION_NOTIFICATION_TYPES),
            'strategy': list(STRATEGY_NOTIFICATION_TYPES),
            'experiment': list(EXPERIMENT_NOTIFICATION_TYPES),
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
        if tasks:
            record_event(
                'agent_tasks_read',
                actor_agent_id=agent_id,
                object_type='agent_task_batch',
                object_id=','.join(str(row['id']) for row in tasks),
                metadata={'task_count': len(tasks), 'message_count': len(messages)},
                cursor=cursor,
            )
        record_event(
            'agent_heartbeat',
            actor_agent_id=agent_id,
            object_type='agent',
            object_id=agent_id,
            metadata={'unread_message_count': unread_message_count, 'pending_task_count': pending_task_count},
            cursor=cursor,
        )

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
        agent_name = data.name.strip()
        if not agent_name:
            raise HTTPException(status_code=400, detail='Agent name is required')

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('SELECT id FROM agents WHERE TRIM(name) = ?', (agent_name,))
            if cursor.fetchone():
                raise HTTPException(status_code=400, detail='Agent name already exists')

            password_hash = hash_password(data.password)
            wallet = validate_address(data.wallet_address) if data.wallet_address else ''

            cursor.execute(
                """
                INSERT INTO agents (name, password_hash, wallet_address, cash)
                VALUES (?, ?, ?, ?)
                """,
                (agent_name, password_hash, wallet, data.initial_balance),
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
            record_event(
                'agent_registered',
                actor_agent_id=agent_id,
                object_type='agent',
                object_id=agent_id,
                metadata={'name': agent_name, 'initial_balance': data.initial_balance, 'position_count': len(data.positions or [])},
                cursor=cursor,
            )

            conn.commit()
            conn.close()

            try:
                experiment_assignments = variant_for_agent(agent_id)
            except Exception as exc:
                print(f"[Experiment Assignment Error] agent_registered={agent_id}: {exc}")
                experiment_assignments = []

            return {
                'token': token,
                'agent_id': agent_id,
                'name': agent_name,
                'initial_balance': data.initial_balance,
                'experiment_assignments': experiment_assignments,
            }
        except HTTPException:
            conn.close()
            raise
        except Exception as exc:
            conn.close()
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post('/api/claw/agents/login')
    async def agent_login(data: AgentLogin):
        row = _get_agent_by_name(data.name)

        if not row or not verify_password(data.password, row['password_hash']):
            raise HTTPException(status_code=401, detail='Invalid credentials')

        token = _get_or_issue_agent_token(row)

        return {'token': token, 'agent_id': row['id'], 'name': row['name']}

    @app.post('/api/claw/agents/token-recovery/request')
    async def request_agent_token_recovery(data: AgentTokenRecoveryRequest):
        agent = _resolve_agent_recovery_target(data.agent_id, data.name)
        expires_at_dt = datetime.now(timezone.utc) + timedelta(minutes=10)
        expires_at = expires_at_dt.isoformat().replace('+00:00', 'Z')
        nonce = secrets.token_urlsafe(18)
        challenge = build_agent_token_recovery_challenge(
            agent_id=agent['id'],
            agent_name=agent['name'],
            wallet_address=agent['wallet_address'],
            nonce=nonce,
            expires_at=expires_at,
        )
        ctx.agent_token_recovery_requests[agent['id']] = {
            'challenge': challenge,
            'expires_at': expires_at_dt,
        }

        return {
            'success': True,
            'agent_id': agent['id'],
            'name': agent['name'],
            'challenge': challenge,
            'expires_at': expires_at,
        }

    @app.post('/api/claw/agents/token-recovery/confirm')
    async def confirm_agent_token_recovery(data: AgentTokenRecoveryConfirm):
        agent = _resolve_agent_recovery_target(data.agent_id, data.name)
        recovery_request = ctx.agent_token_recovery_requests.get(agent['id'])
        if not recovery_request:
            raise HTTPException(status_code=400, detail='No active token recovery request')

        expires_at_dt = recovery_request.get('expires_at')
        if not expires_at_dt or expires_at_dt < datetime.now(timezone.utc):
            ctx.agent_token_recovery_requests.pop(agent['id'], None)
            raise HTTPException(status_code=400, detail='Token recovery challenge expired')

        expected_challenge = recovery_request.get('challenge')
        if expected_challenge != data.challenge:
            raise HTTPException(status_code=400, detail='Token recovery challenge mismatch')

        recovered_address = recover_signed_address(data.challenge, data.signature)
        if recovered_address != agent['wallet_address']:
            raise HTTPException(status_code=401, detail='Wallet signature verification failed')

        token = _issue_agent_token(agent['id'])
        ctx.agent_token_recovery_requests.pop(agent['id'], None)
        return {'token': token, 'agent_id': agent['id'], 'name': agent['name']}

    @app.post('/api/claw/agents/password-reset/request')
    async def request_password_reset(data: AgentPasswordResetRequest):
        agent = _resolve_agent_recovery_target(data.agent_id, data.name)
        expires_at_dt = datetime.now(timezone.utc) + timedelta(minutes=10)
        expires_at = expires_at_dt.isoformat().replace('+00:00', 'Z')
        nonce = secrets.token_urlsafe(18)
        challenge = build_agent_password_reset_challenge(
            agent_id=agent['id'],
            agent_name=agent['name'],
            wallet_address=agent['wallet_address'],
            nonce=nonce,
            expires_at=expires_at,
        )

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE agents SET password_reset_token = ?, password_reset_expires_at = ? WHERE id = ?',
            (challenge, expires_at, agent['id']),
        )
        conn.commit()
        conn.close()

        return {
            'success': True,
            'agent_id': agent['id'],
            'name': agent['name'],
            'challenge': challenge,
            'expires_at': expires_at,
        }

    @app.post('/api/claw/agents/password-reset/confirm')
    async def confirm_password_reset(data: AgentPasswordResetConfirm):
        agent = _resolve_agent_recovery_target(data.agent_id, data.name)

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT password_reset_token, password_reset_expires_at FROM agents WHERE id = ?',
            (agent['id'],),
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=400, detail='Agent not found')

        stored_challenge = row['password_reset_token']
        stored_expires_at = row['password_reset_expires_at']
        conn.close()

        if not stored_challenge or stored_challenge != data.challenge:
            raise HTTPException(status_code=400, detail='Invalid password reset challenge')

        if not stored_expires_at:
            raise HTTPException(status_code=400, detail='No active password reset request')

        expires_at_dt = datetime.fromisoformat(stored_expires_at.replace('Z', '+00:00'))
        if expires_at_dt < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail='Password reset challenge expired')

        recovered_address = recover_signed_address(data.challenge, data.signature)
        if recovered_address != agent['wallet_address']:
            raise HTTPException(status_code=401, detail='Wallet signature verification failed')

        if len(data.new_password) < 8:
            raise HTTPException(status_code=400, detail='Password must be at least 8 characters')

        new_password_hash = hash_password(data.new_password)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE agents SET password_hash = ?, password_reset_token = NULL, password_reset_expires_at = NULL WHERE id = ?',
            (new_password_hash, agent['id']),
        )
        conn.commit()
        conn.close()

        return {'success': True, 'message': 'Password has been reset successfully'}

    @app.get('/api/claw/agents/me')
    async def get_agent_info(authorization: str = Header(None)):
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail='Invalid token')

        try:
            experiment_assignments = variant_for_agent(agent['id'])
        except Exception:
            experiment_assignments = []

        return {
            'id': agent['id'],
            'name': agent['name'],
            'token': token,
            'wallet_address': agent.get('wallet_address'),
            'points': agent.get('points', 0),
            'cash': agent.get('cash', 100000.0),
            'reputation_score': agent.get('reputation_score', 0),
            'experiment_assignments': experiment_assignments,
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
