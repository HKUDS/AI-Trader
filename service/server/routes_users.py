import random
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Header, HTTPException

from database import get_db_connection
from routes_models import (
    PointsExchangeRequest,
    PointsTransferRequest,
    UserLoginRequest,
    UserRegisterRequest,
    UserSendCodeRequest,
)
from routes_shared import RouteContext
from services import _create_user_session, _get_agent_by_token, _get_user_by_token
from utils import _extract_token, hash_password, verify_password


EXCHANGE_RATE = 1000


def register_user_routes(app: FastAPI, ctx: RouteContext) -> None:
    @app.post('/api/users/send-code')
    async def send_verification_code(data: UserSendCodeRequest):
        code = f'{random.randint(0, 999999):06d}'
        ctx.verification_codes[data.email] = {
            'code': code,
            'expires_at': datetime.now(timezone.utc) + timedelta(minutes=5),
        }
        print(f'[Email] Verification code for {data.email}: {code}')
        return {'success': True, 'message': 'Code sent'}

    @app.post('/api/users/register')
    async def user_register(data: UserRegisterRequest):
        if data.email not in ctx.verification_codes:
            raise HTTPException(status_code=400, detail='No code sent')

        stored = ctx.verification_codes[data.email]
        if stored['expires_at'] < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail='Code expired')
        if stored['code'] != data.code:
            raise HTTPException(status_code=400, detail='Invalid code')

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM users WHERE email = ?', (data.email,))
        if cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=400, detail='User already exists')

        password_hash = hash_password(data.password)
        cursor.execute(
            """
            INSERT INTO users (email, password_hash)
            VALUES (?, ?)
            """,
            (data.email, password_hash),
        )
        user_id = cursor.lastrowid
        token = _create_user_session(user_id)

        conn.commit()
        conn.close()
        del ctx.verification_codes[data.email]

        return {'success': True, 'token': token, 'user_id': user_id}

    @app.post('/api/users/login')
    async def user_login(data: UserLoginRequest):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE email = ?', (data.email,))
        row = cursor.fetchone()
        conn.close()

        if not row or not verify_password(data.password, row['password_hash']):
            raise HTTPException(status_code=401, detail='Invalid credentials')

        token = _create_user_session(row['id'])
        return {'token': token, 'user_id': row['id'], 'email': row['email']}

    @app.get('/api/users/me')
    async def get_user_info(authorization: str = Header(None)):
        token = _extract_token(authorization)
        user = _get_user_by_token(token)
        if not user:
            raise HTTPException(status_code=401, detail='Invalid token')

        return {
            'id': user['id'],
            'email': user['email'],
            'wallet_address': user.get('wallet_address'),
            'points': user.get('points', 0),
        }

    @app.get('/api/users/points')
    async def get_points_balance(authorization: str = Header(None)):
        token = _extract_token(authorization)
        user = _get_user_by_token(token)
        if not user:
            raise HTTPException(status_code=401, detail='Invalid token')

        return {'points': user.get('points', 0)}

    @app.post('/api/agents/points/exchange')
    async def exchange_points_for_cash(data: PointsExchangeRequest, authorization: str = Header(None)):
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail='Invalid token')

        if data.amount <= 0:
            raise HTTPException(status_code=400, detail='Amount must be positive')

        current_points = agent.get('points', 0)
        if current_points < data.amount:
            raise HTTPException(
                status_code=400,
                detail=f'Insufficient points. Current: {current_points}, Requested: {data.amount}',
            )

        cash_to_add = data.amount * EXCHANGE_RATE
        current_cash = agent.get('cash', 0)

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE agents
            SET points = points - ?, cash = cash + ?, deposited = deposited + ?
            WHERE id = ?
            """,
            (data.amount, cash_to_add, cash_to_add, agent['id']),
        )
        conn.commit()
        conn.close()

        return {
            'success': True,
            'points_exchanged': data.amount,
            'cash_added': cash_to_add,
            'remaining_points': current_points - data.amount,
            'total_cash': current_cash + cash_to_add,
        }

    @app.get('/api/users/points/history')
    async def get_points_history(authorization: str = Header(None), limit: int = 50):
        token = _extract_token(authorization)
        user = _get_user_by_token(token)
        if not user:
            raise HTTPException(status_code=401, detail='Invalid token')

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM points_transactions
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user['id'], limit),
        )
        rows = cursor.fetchall()
        conn.close()

        return {'transactions': [dict(row) for row in rows]}

    @app.post('/api/users/points/transfer')
    async def transfer_points(data: PointsTransferRequest, authorization: str = Header(None)):
        token = _extract_token(authorization)
        user = _get_user_by_token(token)
        if not user:
            raise HTTPException(status_code=401, detail='Invalid token')

        if data.amount <= 0:
            raise HTTPException(status_code=400, detail='Invalid amount')
        if user['points'] < data.amount:
            raise HTTPException(status_code=400, detail='Insufficient points')

        from_user_id = user['id']
        to_user_id = data.to_user_id
        if from_user_id == to_user_id:
            raise HTTPException(status_code=400, detail='Cannot transfer to yourself')

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET points = points - ? WHERE id = ?', (data.amount, from_user_id))
        cursor.execute('UPDATE users SET points = points + ? WHERE id = ?', (data.amount, to_user_id))
        cursor.execute(
            """
            INSERT INTO points_transactions (user_id, amount, type, description)
            VALUES (?, ?, 'transfer', ?)
            """,
            (from_user_id, -data.amount, f'Transfer to user {to_user_id}'),
        )
        cursor.execute(
            """
            INSERT INTO points_transactions (user_id, amount, type, description)
            VALUES (?, ?, 'transfer', ?)
            """,
            (to_user_id, data.amount, f'Transfer from user {from_user_id}'),
        )
        conn.commit()
        conn.close()

        return {'success': True, 'amount': data.amount}
