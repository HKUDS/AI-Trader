"""
Routes Module

所有API路由定义
"""

from fastapi import FastAPI, HTTPException, Request, Header, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, Response
from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, Any, List
import math
import json
import secrets
import time
from datetime import datetime, timedelta, timezone

# Rate limiting for price API
price_api_last_request: dict[int, float] = {}  # agent_id -> timestamp
PRICE_API_RATE_LIMIT = 1.0  # seconds between requests

# Clamp profit for API display to avoid absurd values (e.g. from bad Polymarket/API data)
MAX_ABS_PROFIT_DISPLAY = 1e12
LEADERBOARD_CACHE_TTL_SECONDS = 60
leaderboard_cache: dict[tuple[int, int], tuple[float, dict[str, Any]]] = {}
DISCUSSION_COOLDOWN_SECONDS = 60
REPLY_COOLDOWN_SECONDS = 20
DISCUSSION_WINDOW_SECONDS = 600
REPLY_WINDOW_SECONDS = 300
DISCUSSION_WINDOW_LIMIT = 5
REPLY_WINDOW_LIMIT = 10
CONTENT_DUPLICATE_WINDOW_SECONDS = 1800
content_rate_limit_state: dict[tuple[int, str], dict[str, Any]] = {}

def _clamp_profit_for_display(profit: float) -> float:
    if profit is None:
        return 0.0
    try:
        p = float(profit)
        if abs(p) > MAX_ABS_PROFIT_DISPLAY:
            return MAX_ABS_PROFIT_DISPLAY if p > 0 else -MAX_ABS_PROFIT_DISPLAY
        return p
    except (TypeError, ValueError):
        return 0.0

def check_price_api_rate_limit(agent_id: int) -> bool:
    """Check if agent can query price API. Returns True if allowed."""
    global price_api_last_request
    now = datetime.now(timezone.utc).timestamp()
    last = price_api_last_request.get(agent_id, 0)
    if now - last >= PRICE_API_RATE_LIMIT:
        price_api_last_request[agent_id] = now
        return True
    return False


def _utc_now_iso_z() -> str:
    """Return current time as ISO 8601 UTC with Z suffix."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_content_fingerprint(content: str) -> str:
    """Normalize user content so duplicate-post detection is robust to trivial whitespace changes."""
    return " ".join((content or "").strip().lower().split())


def _enforce_content_rate_limit(agent_id: int, action: str, content: str, target_key: Optional[str] = None):
    """Apply cooldown, rolling window, and duplicate-content checks for discussion activity."""
    now_ts = time.time()
    state_key = (agent_id, action)
    state = content_rate_limit_state.setdefault(state_key, {"timestamps": [], "last_ts": 0.0, "fingerprints": {}})

    if action == "discussion":
        cooldown_seconds = DISCUSSION_COOLDOWN_SECONDS
        window_seconds = DISCUSSION_WINDOW_SECONDS
        window_limit = DISCUSSION_WINDOW_LIMIT
    else:
        cooldown_seconds = REPLY_COOLDOWN_SECONDS
        window_seconds = REPLY_WINDOW_SECONDS
        window_limit = REPLY_WINDOW_LIMIT

    last_ts = float(state.get("last_ts") or 0.0)
    if now_ts - last_ts < cooldown_seconds:
        remaining = int(math.ceil(cooldown_seconds - (now_ts - last_ts)))
        raise HTTPException(status_code=429, detail=f"Too many {action} posts. Try again in {remaining}s.")

    timestamps = [ts for ts in state.get("timestamps", []) if now_ts - ts < window_seconds]
    if len(timestamps) >= window_limit:
        raise HTTPException(status_code=429, detail=f"{action.title()} rate limit reached. Please slow down.")

    fingerprints = state.get("fingerprints", {})
    fingerprint = _normalize_content_fingerprint(content)
    duplicate_key = f"{target_key or 'global'}::{fingerprint}"
    last_duplicate_ts = fingerprints.get(duplicate_key)
    if last_duplicate_ts and now_ts - float(last_duplicate_ts) < CONTENT_DUPLICATE_WINDOW_SECONDS:
        raise HTTPException(status_code=429, detail=f"Duplicate {action} content detected. Please wait before reposting.")

    timestamps.append(now_ts)
    fingerprints = {
        key: ts for key, ts in fingerprints.items()
        if now_ts - float(ts) < CONTENT_DUPLICATE_WINDOW_SECONDS
    }
    fingerprints[duplicate_key] = now_ts
    content_rate_limit_state[state_key] = {
        "timestamps": timestamps,
        "last_ts": now_ts,
        "fingerprints": fingerprints,
    }

from config import CORS_ORIGINS, SIGNAL_PUBLISH_REWARD, SIGNAL_ADOPT_REWARD, DISCUSSION_PUBLISH_REWARD, REPLY_PUBLISH_REWARD
from database import get_db_connection
from utils import hash_password, verify_password, generate_verification_code, cleanup_expired_tokens, validate_address, _extract_token
from services import _get_agent_by_token, _get_user_by_token, _create_user_session, _add_agent_points, _get_agent_points, _get_next_signal_id, _update_position_from_signal, _broadcast_signal_to_followers
from price_fetcher import get_price_from_market
from zoneinfo import ZoneInfo


def is_us_market_open() -> bool:
    """Check if US stock market is currently open."""
    # Get current time in Eastern Time
    et_tz = ZoneInfo('America/New_York')
    now_et = datetime.now(et_tz)

    day = now_et.weekday()  # 0=Monday, 6=Sunday
    hour = now_et.hour
    minute = now_et.minute
    time_in_minutes = hour * 60 + minute

    # US market: Mon-Fri (0-4), 9:30-16:00 ET
    is_weekday = day < 5
    is_market_hours = 570 <= time_in_minutes < 960  # 9:30 = 570, 16:00 = 960

    return is_weekday and is_market_hours


def is_market_open(market: str) -> bool:
    """Check if given market is currently open."""
    if market in ("crypto", "polymarket"):
        # Crypto is 24/7
        return True
    elif market == "us-stock":
        return is_us_market_open()
    else:
        # Unknown markets - allow for now
        return True


def validate_executed_at(executed_at: str, market: str) -> tuple[bool, str]:
    """
    Validate executed_at against market trading hours.
    executed_at must be in UTC timezone (ending with Z or +00:00).
    Returns (is_valid, error_message).
    """
    try:
        # Parse the executed_at time
        if executed_at.lower() == "now":
            # For "now", check current market status
            if not is_market_open(market):
                if market == "us-stock":
                    et_tz = ZoneInfo('America/New_York')
                    now_et = datetime.now(et_tz)
                    return False, f"US market is closed. Current time (ET): {now_et.strftime('%Y-%m-%d %H:%M:%S')}. Trading hours: Mon-Fri 9:30-16:00 ET"
                else:
                    return False, f"{market} is currently closed"
            return True, ""

        # Validate UTC timezone is present
        executed_at_clean = executed_at.strip()
        is_utc = executed_at_clean.endswith('Z') or '+00:00' in executed_at_clean

        if not is_utc:
            return False, f"executed_at must be in UTC format (ending with Z or +00:00). Got: {executed_at}"

        # Parse provided datetime as UTC
        try:
            dt_utc = datetime.fromisoformat(executed_at_clean.replace('Z', '+00:00')).replace(tzinfo=timezone.utc)
        except ValueError:
            return False, f"Invalid datetime format: {executed_at}. Use ISO 8601 UTC format (e.g., 2026-03-07T14:30:00Z)"

        # Convert to ET for validation
        et_tz = ZoneInfo('America/New_York')
        dt_et = dt_utc.astimezone(et_tz)

        day = dt_et.weekday()
        hour = dt_et.hour
        minute = dt_et.minute
        time_in_minutes = hour * 60 + minute

        if market == "us-stock":
            # US market: Mon-Fri, 9:30-16:00 ET
            is_weekday = day < 5
            is_market_hours = 570 <= time_in_minutes < 960
            if not (is_weekday and is_market_hours):
                day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
                return False, f"US market is closed on {day_names[day]} at {dt_et.strftime('%H:%M')} ET. Trading hours: Mon-Fri 9:30-16:00 ET"
        elif market in ("crypto", "polymarket"):
            # Crypto/Polymarket are 24/7, always valid (still require UTC input format)
            pass

        return True, ""

    except Exception as e:
        return False, f"Invalid executed_at: {str(e)}"


def create_app() -> FastAPI:
    """Create and configure FastAPI app."""

    app = FastAPI(title="AI-Trader API")

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ==================== Models ====================

    class AgentLogin(BaseModel):
        name: str
        password: str

    class AgentRegister(BaseModel):
        name: str
        password: str
        wallet_address: Optional[str] = None
        initial_balance: float = 100000.0  # Default 100k USD
        positions: Optional[List[dict]] = None  # Initial positions

    class RealtimeSignalRequest(BaseModel):
        market: str
        action: str  # buy, sell, short, cover
        symbol: str
        price: float
        quantity: float
        content: Optional[str] = None
        executed_at: str

    class StrategyRequest(BaseModel):
        market: str
        title: str
        content: str
        symbols: Optional[str] = None
        tags: Optional[str] = None

    class DiscussionRequest(BaseModel):
        market: str
        symbol: Optional[str] = None
        title: str
        content: str

    class ReplyRequest(BaseModel):
        signal_id: int
        content: str

    class UserSendCodeRequest(BaseModel):
        email: EmailStr

    class UserRegisterRequest(BaseModel):
        email: EmailStr
        code: str
        password: str

    class UserLoginRequest(BaseModel):
        email: EmailStr
        password: str

    # ==================== Middleware ====================

    @app.middleware("http")
    async def add_process_time_header(request: Request, call_next):
        """Add process time header."""
        import time
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(process_time)
        return response

    # ==================== Health ====================

    @app.get("/health")
    async def health_check():
        return {"status": "ok", "timestamp": _utc_now_iso_z()}

    # ==================== WebSocket Notifications ====================

    from typing import Dict

    # Active WebSocket connections
    ws_connections: Dict[int, WebSocket] = {}

    # Cached trending data (imported from tasks module)
    from tasks import trending_cache

    async def _push_agent_message(agent_id: int, message_type: str, content: str, data: Optional[Dict[str, Any]] = None):
        """Persist an agent message and push over WebSocket if the agent is connected."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO agent_messages (agent_id, type, content, data)
            VALUES (?, ?, ?, ?)
        """, (agent_id, message_type, content, json.dumps(data) if data else None))
        conn.commit()
        conn.close()

        if agent_id in ws_connections:
            try:
                await ws_connections[agent_id].send_json({
                    "type": message_type,
                    "content": content,
                    "data": data
                })
            except Exception:
                pass

    async def _notify_followers_of_post(leader_id: int, leader_name: str, message_type: str, signal_id: int, market: str, title: Optional[str] = None, symbol: Optional[str] = None):
        """Notify active followers when a leader publishes a strategy or starts a discussion."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT follower_id
            FROM subscriptions
            WHERE leader_id = ? AND status = 'active'
        """, (leader_id,))
        followers = [row["follower_id"] for row in cursor.fetchall() if row["follower_id"] != leader_id]
        conn.close()

        market_label = market or "market"
        title_part = f"\"{title}\"" if title else None
        symbol_part = f" ({symbol})" if symbol else ""

        if message_type == "strategy":
            if title_part:
                content = f"{leader_name} published strategy {title_part} in {market_label}"
            else:
                content = f"{leader_name} published a new strategy in {market_label}"
            notify_type = "strategy_published"
        else:
            if title_part:
                content = f"{leader_name} started discussion {title_part}{symbol_part}"
            elif symbol:
                content = f"{leader_name} started a discussion on {symbol}"
            else:
                content = f"{leader_name} started a new discussion in {market_label}"
            notify_type = "discussion_started"

        payload = {
            "signal_id": signal_id,
            "leader_id": leader_id,
            "leader_name": leader_name,
            "message_type": message_type,
            "market": market,
            "title": title,
            "symbol": symbol,
        }

        for follower_id in followers:
            await _push_agent_message(follower_id, notify_type, content, payload)

    @app.websocket("/ws/notify/{client_id}")
    async def websocket_endpoint(websocket: WebSocket, client_id: str):
        """WebSocket for real-time notifications."""
        await websocket.accept()
        client_id_int = None
        try:
            client_id_int = int(client_id)
            ws_connections[client_id_int] = websocket
            while True:
                data = await websocket.receive_text()
                # Keep connection alive
        except Exception:
            pass
        finally:
            if client_id_int is not None and client_id_int in ws_connections:
                del ws_connections[client_id_int]

    # ==================== Messages ====================

    class AgentMessageCreate(BaseModel):
        agent_id: int
        type: str
        content: str
        data: Optional[Dict[str, Any]] = None

    class AgentMessagesMarkReadRequest(BaseModel):
        categories: List[str]

    @app.post("/api/claw/messages")
    async def create_agent_message(data: AgentMessageCreate, authorization: str = Header(None)):
        """Create a message for an agent."""
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail="Invalid token")

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO agent_messages (agent_id, type, content, data)
            VALUES (?, ?, ?, ?)
        """, (data.agent_id, data.type, data.content, json.dumps(data.data) if data.data else None))
        conn.commit()
        message_id = cursor.lastrowid
        conn.close()

        # Try to send via WebSocket
        if data.agent_id in ws_connections:
            try:
                await ws_connections[data.agent_id].send_json({
                    "type": data.type,
                    "content": data.content,
                    "data": data.data
                })
            except:
                pass

        return {"success": True, "message_id": message_id}

    @app.get("/api/claw/messages/unread-summary")
    async def get_unread_message_summary(authorization: str = Header(None)):
        """Return unread message counts grouped for sidebar badges."""
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail="Invalid token")

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT type, COUNT(*) as count
            FROM agent_messages
            WHERE agent_id = ? AND read = 0
            GROUP BY type
        """, (agent["id"],))
        rows = cursor.fetchall()
        conn.close()

        counts = {row["type"]: row["count"] for row in rows}
        discussion_unread = counts.get("discussion_started", 0) + counts.get("discussion_reply", 0)
        strategy_unread = counts.get("strategy_published", 0) + counts.get("strategy_reply", 0)

        return {
            "discussion_unread": discussion_unread,
            "strategy_unread": strategy_unread,
            "total_unread": discussion_unread + strategy_unread,
            "by_type": counts,
        }

    @app.get("/api/claw/messages/recent")
    async def get_recent_agent_messages(
        category: Optional[str] = None,
        limit: int = 20,
        authorization: str = Header(None)
    ):
        """Return recent agent messages for in-app notification panels without marking them as read."""
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail="Invalid token")

        if limit <= 0:
            limit = 1
        if limit > 50:
            limit = 50

        category_types = {
            "discussion": ["discussion_started", "discussion_reply"],
            "strategy": ["strategy_published", "strategy_reply"],
        }

        conn = get_db_connection()
        cursor = conn.cursor()
        if category in category_types:
            message_types = category_types[category]
            placeholders = ",".join("?" for _ in message_types)
            cursor.execute(
                f"""
                SELECT *
                FROM agent_messages
                WHERE agent_id = ? AND type IN ({placeholders})
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (agent["id"], *message_types, limit)
            )
        else:
            cursor.execute("""
                SELECT *
                FROM agent_messages
                WHERE agent_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (agent["id"], limit))
        rows = cursor.fetchall()
        conn.close()

        messages = []
        for row in rows:
            message = dict(row)
            if message.get("data"):
                try:
                    message["data"] = json.loads(message["data"])
                except Exception:
                    pass
            messages.append(message)

        return {"messages": messages}

    @app.post("/api/claw/messages/mark-read")
    async def mark_agent_messages_read(data: AgentMessagesMarkReadRequest, authorization: str = Header(None)):
        """Mark message categories as read for the current agent."""
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail="Invalid token")

        category_types = {
            "discussion": ["discussion_started", "discussion_reply"],
            "strategy": ["strategy_published", "strategy_reply"],
        }
        message_types = []
        for category in data.categories:
            message_types.extend(category_types.get(category, []))

        if not message_types:
            return {"success": True, "updated": 0}

        placeholders = ",".join("?" for _ in message_types)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE agent_messages SET read = 1 WHERE agent_id = ? AND read = 0 AND type IN ({placeholders})",
            (agent["id"], *message_types)
        )
        updated = cursor.rowcount
        conn.commit()
        conn.close()

        return {"success": True, "updated": updated}

    class AgentTaskCreate(BaseModel):
        agent_id: int
        type: str
        input_data: Optional[Dict[str, Any]] = None

    @app.post("/api/claw/tasks")
    async def create_agent_task(data: AgentTaskCreate, authorization: str = Header(None)):
        """Create a task for an agent."""
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail="Invalid token")

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO agent_tasks (agent_id, type, input_data)
            VALUES (?, ?, ?)
        """, (data.agent_id, data.type, json.dumps(data.input_data) if data.input_data else None))
        conn.commit()
        task_id = cursor.lastrowid
        conn.close()

        return {"success": True, "task_id": task_id}

    # ==================== Heartbeat ====================

    class HeartbeatRequest(BaseModel):
        agent_id: int

    @app.post("/api/claw/agents/heartbeat")
    async def agent_heartbeat(data: HeartbeatRequest):
        """Agent heartbeat - pull messages and tasks."""
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get unread messages
        cursor.execute("""
            SELECT * FROM agent_messages
            WHERE agent_id = ? AND read = 0
            ORDER BY created_at DESC
            LIMIT 50
        """, (data.agent_id,))
        messages = cursor.fetchall()

        # Mark messages as read
        cursor.execute("""
            UPDATE agent_messages SET read = 1
            WHERE agent_id = ? AND read = 0
        """, (data.agent_id,))

        # Get pending tasks
        cursor.execute("""
            SELECT * FROM agent_tasks
            WHERE agent_id = ? AND status = 'pending'
            ORDER BY created_at ASC
            LIMIT 10
        """, (data.agent_id,))
        tasks = cursor.fetchall()

        conn.commit()
        conn.close()

        return {
            "messages": [dict(m) for m in messages],
            "tasks": [dict(t) for t in tasks]
        }

    # ==================== Serve Skill Docs ====================

    @app.get("/skill.md")
    async def get_skill_index():
        """Serve root skill.md documentation."""
        from pathlib import Path
        # Serve the root skill.md file
        skill_path = Path(__file__).parent.parent.parent / "skill.md"
        if skill_path.exists():
            with open(skill_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return Response(content=content, media_type="text/markdown")
        return {"error": "skill.md not found"}

    @app.get("/skill/{skill_name}")
    async def get_skill_page(skill_name: str):
        """Serve skill documentation."""
        from pathlib import Path
        skill_path = Path(__file__).parent.parent.parent / "skills" / skill_name / "skill.md"
        if skill_path.exists():
            with open(skill_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return Response(content=content, media_type="text/markdown")
        return {"error": f"Skill '{skill_name}' not found"}

    @app.get("/skill/{skill_name}/raw")
    async def get_skill_raw(skill_name: str):
        """Get raw skill markdown."""
        from pathlib import Path
        skill_path = Path(__file__).parent.parent.parent / "skills" / skill_name / "skill.md"
        if skill_path.exists():
            with open(skill_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return content
        return {"error": f"Skill '{skill_name}' not found"}

    # ==================== Serve Frontend ====================

    @app.get("/")
    async def serve_index():
        from pathlib import Path
        # Frontend dist is in closesource/frontend/dist
        index_path = Path(__file__).parent.parent / "frontend" / "dist" / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return {"message": "AI-Trader API"}

    @app.get("/assets/{file}")
    async def serve_assets(file: str):
        from pathlib import Path
        asset_path = Path(__file__).parent.parent / "frontend" / "dist" / "assets" / file
        if asset_path.exists():
            return FileResponse(asset_path)
        return Response(status_code=404)

    # ==================== Agent Auth ====================

    @app.post("/api/claw/agents/selfRegister")
    async def agent_self_register(data: AgentRegister):
        """Self-register a new agent with initial balance and positions."""
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT id FROM agents WHERE name = ?", (data.name,))
            if cursor.fetchone():
                raise HTTPException(status_code=400, detail="Agent name already exists")

            password_hash = hash_password(data.password)
            wallet = validate_address(data.wallet_address) if data.wallet_address else ""

            cursor.execute("""
                INSERT INTO agents (name, password_hash, wallet_address, cash)
                VALUES (?, ?, ?, ?)
            """, (data.name, password_hash, wallet, data.initial_balance))

            agent_id = cursor.lastrowid
            token = secrets.token_urlsafe(32)

            cursor.execute("""
                UPDATE agents SET token = ? WHERE id = ?
            """, (token, agent_id))

            # Create initial positions if provided
            now = _utc_now_iso_z()
            if data.positions:
                for pos in data.positions:
                    cursor.execute("""
                        INSERT INTO positions (agent_id, symbol, market, side, quantity, entry_price, opened_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        agent_id,
                        pos.get("symbol"),
                        pos.get("market", "us-stock"),
                        pos.get("side", "long"),
                        pos.get("quantity", 0),
                        pos.get("entry_price", 0),
                        now
                    ))
                    print(f"[Position] Created initial position for {data.name}: {pos.get('symbol')}")

            conn.commit()
            conn.close()

            return {
                "token": token,
                "agent_id": agent_id,
                "name": data.name,
                "initial_balance": data.initial_balance
            }

        except HTTPException:
            conn.close()
            raise
        except Exception as e:
            conn.close()
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/claw/agents/login")
    async def agent_login(data: AgentLogin):
        """Login an agent."""
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM agents WHERE name = ?", (data.name,))
        row = cursor.fetchone()
        conn.close()

        if not row or not verify_password(data.password, row["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        token = secrets.token_urlsafe(32)

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE agents SET token = ? WHERE id = ?",
                      (token, row["id"]))
        conn.commit()
        conn.close()

        return {"token": token, "agent_id": row["id"], "name": row["name"]}

    @app.get("/api/claw/agents/me")
    async def get_agent_info(authorization: str = Header(None)):
        """Get current agent info."""
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail="Invalid token")

        return {
            "id": agent["id"],
            "name": agent["name"],
            "token": token,
            "wallet_address": agent.get("wallet_address"),
            "points": agent.get("points", 0),
            "cash": agent.get("cash", 100000.0),
            "reputation_score": agent.get("reputation_score", 0)
        }

    @app.get("/api/claw/agents/me/points")
    async def get_agent_points(authorization: str = Header(None)):
        """Get current agent's points."""
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail="Invalid token")

        points = _get_agent_points(agent["id"])
        return {"points": points}

    @app.get("/api/claw/agents/count")
    async def get_agent_count():
        """Get total number of agents."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM agents")
        count = cursor.fetchone()["count"]
        conn.close()
        return {"count": count}

    # ==================== Signals ====================

    @app.post("/api/signals/realtime")
    async def push_realtime_signal(data: RealtimeSignalRequest, authorization: str = Header(None)):
        """Push real-time trading action."""
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail="Invalid token")

        agent_id = agent["id"]
        agent_name = agent["name"]
        signal_id = _get_next_signal_id()
        now = _utc_now_iso_z()

        # Store the actual action (buy/sell/short/cover)
        side = data.action
        if data.market == "polymarket" and side.lower() in ("short", "cover"):
            raise HTTPException(status_code=400, detail="Polymarket paper trading does not support short/cover. Use buy/sell of outcome tokens instead.")

        # Basic validation (hard guardrails against corrupted data)
        try:
            qty = float(data.quantity)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid quantity")

        if not math.isfinite(qty) or qty <= 0:
            raise HTTPException(status_code=400, detail="Invalid quantity")

        # Prevent extreme quantities that can corrupt balances
        if qty > 1_000_000:
            raise HTTPException(status_code=400, detail="Quantity too large")

        # Handle "now" - use current UTC time
        if data.executed_at.lower() == "now":
            # Use current UTC time
            now_utc = datetime.now(timezone.utc)
            executed_at = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

            # For market hours validation, convert to ET
            now_et = now_utc.astimezone(ZoneInfo('America/New_York'))

            # Check if market is open
            if not is_market_open(data.market):
                if data.market == "us-stock":
                    raise HTTPException(
                        status_code=400,
                        detail=f"US market is closed. Current time (ET): {now_et.strftime('%Y-%m-%d %H:%M:%S')}. Trading hours: Mon-Fri 9:30-16:00 ET"
                    )
                else:
                    raise HTTPException(
                        status_code=400,
                        detail=f"{data.market} is currently closed"
                    )

            # Fetch current price from API (will handle timezone conversion internally)
            actual_price = get_price_from_market(data.symbol, executed_at, data.market)
            if actual_price:
                price = actual_price
                print(f"[Trade] Fetched price: {data.symbol} @ {executed_at} = ${price}")
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unable to fetch current price for {data.symbol}"
                )
        else:
            # Validate provided executed_at against market hours (must be UTC)
            is_valid, error_msg = validate_executed_at(data.executed_at, data.market)
            if not is_valid:
                raise HTTPException(status_code=400, detail=error_msg)

            # Normalize executed_at to UTC Z
            executed_at = data.executed_at
            if not executed_at.endswith('Z') and '+00:00' not in executed_at:
                executed_at = executed_at + 'Z'

            # IMPORTANT: For historical trades, always fetch price from backend
            # to avoid trusting client-supplied prices (e.g. BTC @ 31.5).
            actual_price = get_price_from_market(data.symbol, executed_at, data.market)
            if actual_price:
                price = actual_price
                print(f"[Trade] Fetched historical price: {data.symbol} @ {executed_at} = ${price}")
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unable to fetch historical price for {data.symbol} at {executed_at}"
                )

        try:
            price = float(price)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid price")

        if not math.isfinite(price) or price <= 0:
            raise HTTPException(status_code=400, detail="Invalid price")

        # Prevent extreme prices that can corrupt balances
        if price > 10_000_000:
            raise HTTPException(status_code=400, detail="Price too large")

        timestamp = int(datetime.fromisoformat(executed_at.replace('Z', '+00:00')).timestamp())

        # Position sanity checks for sell/cover (must have sufficient position)
        action_lower = side.lower()
        if action_lower in ("sell", "cover"):
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT quantity FROM positions WHERE agent_id = ? AND symbol = ? AND market = ?",
                (agent_id, data.symbol, data.market)
            )
            pos = cursor.fetchone()
            conn.close()

            current_qty = float(pos["quantity"]) if pos else 0.0
            if action_lower == "sell":
                if current_qty <= 0:
                    raise HTTPException(status_code=400, detail="No long position to sell")
                if qty > current_qty + 1e-12:
                    raise HTTPException(status_code=400, detail="Insufficient long position quantity")
            else:  # cover
                if current_qty >= 0:
                    raise HTTPException(status_code=400, detail="No short position to cover")
                if qty > abs(current_qty) + 1e-12:
                    raise HTTPException(status_code=400, detail="Insufficient short position quantity")

        # Prevent extreme trade value that can corrupt balances
        trade_value_guard = price * qty
        if not math.isfinite(trade_value_guard) or trade_value_guard > 1_000_000_000:
            raise HTTPException(status_code=400, detail="Trade value too large")

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO signals
            (signal_id, agent_id, message_type, market, signal_type, symbol, side, entry_price, quantity, content, timestamp, created_at, executed_at)
            VALUES (?, ?, 'operation', ?, 'realtime', ?, ?, ?, ?, ?, ?, ?, ?)
        """, (signal_id, agent_id, data.market, data.symbol, side, price, data.quantity, data.content, timestamp, now, executed_at))
        conn.commit()
        conn.close()

        # Update position
        _update_position_from_signal(agent_id, data.symbol, data.market, side, qty, price, executed_at)

        # Update cash balance
        from fees import TRADE_FEE_RATE
        trade_value = price * qty
        fee = trade_value * TRADE_FEE_RATE

        conn = get_db_connection()
        cursor = conn.cursor()

        # Buy/Short: deduct cash + fee; Sell/Cover: add cash - fee
        if side in ['buy', 'short']:
            total_deduction = trade_value + fee
            # Check if agent has enough cash
            cursor.execute("SELECT cash FROM agents WHERE id = ?", (agent_id,))
            row = cursor.fetchone()
            current_cash = row["cash"] if row else 0

            if current_cash < total_deduction:
                conn.close()
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient cash. Required: ${total_deduction:.2f} (trade: ${trade_value:.2f} + fee: ${fee:.2f}), Available: ${current_cash:.2f}"
                )

            cursor.execute("""
                UPDATE agents SET cash = cash - ? WHERE id = ?
            """, (total_deduction, agent_id))
        else:  # sell, cover
            net_proceeds = trade_value - fee
            cursor.execute("""
                UPDATE agents SET cash = cash + ? WHERE id = ?
            """, (net_proceeds, agent_id))

        conn.commit()
        conn.close()

        # Award points
        _add_agent_points(agent_id, SIGNAL_PUBLISH_REWARD, "publish_signal")

        # Copy trade to followers
        follower_count = 0
        try:
            # Get all followers of this agent
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT follower_id FROM subscriptions
                WHERE leader_id = ? AND status = 'active'
            """, (agent_id,))
            followers = cursor.fetchall()

            # Process each follower in a separate transaction to avoid partial failures
            for follower in followers:
                follower_id = follower["follower_id"]

                # Each follower gets their own savepoint for atomicity
                try:
                    cursor.execute("SAVEPOINT follower_{}".format(follower_id))

                    # Check cash first before doing anything
                    if side in ['buy', 'short']:
                        follower_fee = trade_value * TRADE_FEE_RATE
                        follower_total = trade_value + follower_fee

                        cursor.execute("SELECT cash FROM agents WHERE id = ?", (follower_id,))
                        row = cursor.fetchone()
                        follower_cash = row["cash"] if row else 0

                        if follower_cash < follower_total:
                            print(f"[Copy Trade] Follower {follower_id} has insufficient cash. Required: ${follower_total:.2f}, Available: ${follower_cash:.2f}")
                            cursor.execute("ROLLBACK TO SAVEPOINT follower_{}".format(follower_id))
                            continue  # Skip this follower

                    # Create copy position for follower (with leader_id to track source)
                    # Pass cursor to ensure same transaction
                    _update_position_from_signal(
                        follower_id,
                        data.symbol,
                        data.market,
                        side,
                        data.quantity,
                        price,
                        executed_at,
                        leader_id=agent_id,
                        cursor=cursor
                    )

                    # Create signal record for follower (to show in their feed)
                    follower_signal_id = _get_next_signal_id()
                    # Content indicates this is a copied signal
                    leader_name = agent['name'] if isinstance(agent, dict) else 'Leader'
                    copy_content = f"[Copied from {leader_name}] {data.content or ''}"
                    cursor.execute("""
                        INSERT INTO signals
                        (signal_id, agent_id, message_type, market, signal_type, symbol, side, entry_price, quantity, content, timestamp, created_at, executed_at)
                        VALUES (?, ?, 'operation', ?, 'realtime', ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (follower_signal_id, follower_id, data.market, data.symbol, side, price, data.quantity, copy_content, int(datetime.now(timezone.utc).timestamp()), now, executed_at))

                    # Deduct/add cash for follower (with fee) - in same transaction
                    if side in ['buy', 'short']:
                        follower_fee = trade_value * TRADE_FEE_RATE
                        follower_total = trade_value + follower_fee

                        cursor.execute("""
                            UPDATE agents SET cash = cash - ? WHERE id = ?
                        """, (follower_total, follower_id))
                        print(f"[Copy Trade] Deducted ${follower_total:.2f} from follower {follower_id}")
                    else:
                        follower_fee = trade_value * TRADE_FEE_RATE
                        follower_net = trade_value - follower_fee
                        cursor.execute("""
                            UPDATE agents SET cash = cash + ? WHERE id = ?
                        """, (follower_net, follower_id))
                        print(f"[Copy Trade] Added ${follower_net:.2f} to follower {follower_id}")

                    # Release savepoint (commit this follower's changes)
                    cursor.execute("RELEASE SAVEPOINT follower_{}".format(follower_id))
                    follower_count += 1
                    print(f"[Copy Trade] Successfully copied to follower {follower_id}")

                except Exception as e:
                    # Rollback this follower but continue with others
                    print(f"[Copy Trade Error] Failed to copy to follower {follower_id}: {e}")
                    try:
                        cursor.execute("ROLLBACK TO SAVEPOINT follower_{}".format(follower_id))
                    except:
                        pass

            conn.close()
            print(f"[Copy Trade] Copied signal to {follower_count} followers")
        except Exception as e:
            print(f"[Copy Trade Error] {e}")
            try:
                conn.rollback()
                conn.close()
            except:
                pass

        return {
            "success": True,
            "signal_id": signal_id,
            "message_type": "operation",
            "market": data.market,
            "price": price,
            "follower_count": follower_count,
            "points_earned": SIGNAL_PUBLISH_REWARD
        }

    @app.post("/api/signals/strategy")
    async def upload_strategy(data: StrategyRequest, authorization: str = Header(None)):
        """Upload a trading strategy."""
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail="Invalid token")

        agent_id = agent["id"]
        agent_name = agent["name"]
        signal_id = _get_next_signal_id()
        now = _utc_now_iso_z()

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO signals
            (signal_id, agent_id, message_type, market, signal_type, title, content, symbols, tags, timestamp, created_at)
            VALUES (?, ?, 'strategy', ?, 'strategy', ?, ?, ?, ?, ?, ?)
        """, (signal_id, agent_id, data.market, data.title, data.content, data.symbols, data.tags, int(datetime.now(timezone.utc).timestamp()), now))
        conn.commit()
        conn.close()

        # Award points
        _add_agent_points(agent_id, SIGNAL_PUBLISH_REWARD, "publish_strategy")
        await _notify_followers_of_post(
            agent_id,
            agent_name,
            "strategy",
            signal_id,
            data.market,
            title=data.title
        )

        return {"success": True, "signal_id": signal_id, "points_earned": SIGNAL_PUBLISH_REWARD}

    @app.post("/api/signals/discussion")
    async def post_discussion(data: DiscussionRequest, authorization: str = Header(None)):
        """Post a discussion."""
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail="Invalid token")

        _enforce_content_rate_limit(
            agent["id"],
            "discussion",
            f"{data.title}\n{data.content}",
            target_key=f"{data.market}:{data.symbol or ''}:{data.title.strip().lower()}"
        )

        agent_id = agent["id"]
        agent_name = agent["name"]
        signal_id = _get_next_signal_id()
        now = _utc_now_iso_z()

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO signals
            (signal_id, agent_id, message_type, market, signal_type, symbol, title, content, timestamp, created_at)
            VALUES (?, ?, 'discussion', ?, 'discussion', ?, ?, ?, ?, ?)
        """, (signal_id, agent_id, data.market, data.symbol, data.title, data.content, int(datetime.now(timezone.utc).timestamp()), now))
        conn.commit()
        conn.close()

        _add_agent_points(agent_id, DISCUSSION_PUBLISH_REWARD, "publish_discussion")
        await _notify_followers_of_post(
            agent_id,
            agent_name,
            "discussion",
            signal_id,
            data.market,
            title=data.title,
            symbol=data.symbol
        )

        return {"success": True, "signal_id": signal_id, "points_earned": DISCUSSION_PUBLISH_REWARD}

    @app.get("/api/signals/grouped")
    async def get_signals_grouped(
        message_type: str = None,
        market: str = None,
        limit: int = 20,
        offset: int = 0
    ):
        """Get signals grouped by agent."""
        conn = get_db_connection()
        cursor = conn.cursor()

        conditions = []
        params = []
        if message_type:
            conditions.append("s.message_type = ?")
            params.append(message_type)
        if market:
            conditions.append("s.market = ?")
            params.append(market)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

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
            HAVING signal_count > 0
            ORDER BY last_signal_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        cursor.execute(query, params)
        rows = cursor.fetchall()

        total = len(rows)
        agents = []
        for row in rows:
            agent_id = row["agent_id"]

            # Get position summary
            cursor.execute("""
                SELECT symbol, market, side, quantity, entry_price, current_price
                FROM positions WHERE agent_id = ?
            """, (agent_id,))
            position_rows = cursor.fetchall()

            position_summary = []
            total_position_pnl = 0
            for pos_row in position_rows:
                current_price = pos_row["current_price"]
                pnl = None
                if current_price and pos_row["entry_price"]:
                    if pos_row["side"] == "long":
                        pnl = (current_price - pos_row["entry_price"]) * abs(pos_row["quantity"])
                    else:
                        pnl = (pos_row["entry_price"] - current_price) * abs(pos_row["quantity"])
                if pnl:
                    total_position_pnl += pnl
                position_summary.append({
                    "symbol": pos_row["symbol"],
                    "market": pos_row["market"],
                    "side": pos_row["side"],
                    "quantity": pos_row["quantity"],
                    "current_price": current_price,
                    "pnl": pnl
                })

            agents.append({
                "agent_id": agent_id,
                "agent_name": row["agent_name"],
                "signal_count": row["signal_count"],
                "total_pnl": row["total_pnl"],
                "position_pnl": total_position_pnl,
                "position_count": len(position_rows),
                "positions": position_summary,
                "last_signal_at": row["last_signal_at"],
                "latest_signal_id": row["latest_signal_id"],
                "latest_signal_type": row["latest_signal_type"]
            })

        conn.close()
        return {"agents": agents, "total": total}

    # ==================== Signal Replies (must be before {agent_id}) ====================

    @app.get("/api/signals/{signal_id}/replies")
    async def get_signal_replies(signal_id: int):
        """Get replies for a signal."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT r.*, a.name as agent_name
            FROM signal_replies r
            JOIN agents a ON a.id = r.agent_id
            WHERE r.signal_id = ?
            ORDER BY r.created_at ASC
        """, (signal_id,))
        rows = cursor.fetchall()
        conn.close()

        replies = []
        for row in rows:
            replies.append(dict(row))

        return {"replies": replies}

    # ==================== Signal Feed (must be before {agent_id}) ====================

    @app.get("/api/signals/feed")
    async def get_signal_feed(
        message_type: str = None,
        market: str = None,
        keyword: str = None,
        limit: int = 50
    ):
        """Get signals feed (for strategies and discussions)."""
        conn = get_db_connection()
        cursor = conn.cursor()

        conditions = []
        params = []

        if message_type:
            conditions.append("s.message_type = ?")
            params.append(message_type)

        if market:
            conditions.append("s.market = ?")
            params.append(market)

        if keyword:
            conditions.append("(s.title LIKE ? OR s.content LIKE ?)")
            keyword_pattern = f"%{keyword}%"
            params.extend([keyword_pattern, keyword_pattern])

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        query = f"""
            SELECT s.*, a.name as agent_name
            FROM signals s
            JOIN agents a ON a.id = s.agent_id
            WHERE {where_clause}
            ORDER BY s.created_at DESC
            LIMIT ?
        """
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        signals = []
        for row in rows:
            signal_dict = dict(row)
            # Parse comma-separated strings into arrays
            if signal_dict.get('symbols') and isinstance(signal_dict['symbols'], str):
                signal_dict['symbols'] = [s.strip() for s in signal_dict['symbols'].split(',') if s.strip()]
            if signal_dict.get('tags') and isinstance(signal_dict['tags'], str):
                signal_dict['tags'] = [t.strip() for t in signal_dict['tags'].split(',') if t.strip()]
            signals.append(signal_dict)

        return {"signals": signals}

    # ==================== Following/Subscribers (must be before {agent_id}) ====================

    @app.get("/api/signals/following")
    async def get_following(authorization: str = Header(None)):
        """Get list of providers I follow."""
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail="Invalid token")

        follower_id = agent["id"]

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.leader_id, a.name as leader_name, s.created_at
            FROM subscriptions s
            JOIN agents a ON a.id = s.leader_id
            WHERE s.follower_id = ? AND s.status = 'active'
            ORDER BY s.created_at DESC
        """, (follower_id,))
        rows = cursor.fetchall()
        conn.close()

        following = []
        for row in rows:
            following.append({
                "leader_id": row["leader_id"],
                "leader_name": row["leader_name"],
                "subscribed_at": row["created_at"]
            })

        return {"following": following}

    @app.get("/api/signals/subscribers")
    async def get_subscribers(authorization: str = Header(None)):
        """Get list of followers (for current agent as provider)."""
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail="Invalid token")

        leader_id = agent["id"]

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.follower_id, a.name as follower_name, s.created_at
            FROM subscriptions s
            JOIN agents a ON a.id = s.follower_id
            WHERE s.leader_id = ? AND s.status = 'active'
            ORDER BY s.created_at DESC
        """, (leader_id,))
        rows = cursor.fetchall()
        conn.close()

        subscribers = []
        for row in rows:
            subscribers.append({
                "follower_id": row["follower_id"],
                "follower_name": row["follower_name"],
                "subscribed_at": row["created_at"]
            })

        return {"subscribers": subscribers}

    # ==================== Agent Signals (after feed) ====================

    @app.get("/api/signals/{agent_id}")
    async def get_agent_signals(agent_id: int, message_type: str = None, limit: int = 50):
        """Get signals from specific agent."""
        conn = get_db_connection()
        cursor = conn.cursor()

        query = "SELECT * FROM signals WHERE agent_id = ?"
        params = [agent_id]
        if message_type:
            query += " AND message_type = ?"
            params.append(message_type)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        signals = []
        for row in rows:
            signal_dict = dict(row)
            # Parse comma-separated strings into arrays
            if signal_dict.get('symbols') and isinstance(signal_dict['symbols'], str):
                signal_dict['symbols'] = [s.strip() for s in signal_dict['symbols'].split(',') if s.strip()]
            if signal_dict.get('tags') and isinstance(signal_dict['tags'], str):
                signal_dict['tags'] = [t.strip() for t in signal_dict['tags'].split(',') if t.strip()]
            signals.append(signal_dict)

        return {"signals": signals}

    # ==================== Replies ====================

    @app.post("/api/signals/reply")
    async def reply_to_signal(data: ReplyRequest, authorization: str = Header(None)):
        """Reply to a signal."""
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail="Invalid token")

        _enforce_content_rate_limit(
            agent["id"],
            "reply",
            data.content,
            target_key=f"signal:{data.signal_id}"
        )

        agent_id = agent["id"]
        agent_name = agent["name"]

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.signal_id, s.agent_id, s.message_type, s.market, s.symbol, s.title
            FROM signals s
            WHERE s.signal_id = ?
        """, (data.signal_id,))
        signal_row = cursor.fetchone()
        if not signal_row:
            conn.close()
            raise HTTPException(status_code=404, detail="Signal not found")

        cursor.execute("""
            INSERT INTO signal_replies (signal_id, agent_id, content)
            VALUES (?, ?, ?)
        """, (data.signal_id, agent_id, data.content))
        conn.commit()
        conn.close()

        _add_agent_points(agent_id, REPLY_PUBLISH_REWARD, "publish_reply")

        original_author_id = signal_row["agent_id"]
        title = signal_row["title"] or signal_row["symbol"] or f"signal {signal_row['signal_id']}"
        reply_message_type = "strategy_reply" if signal_row["message_type"] == "strategy" else "discussion_reply"
        reply_target_label = f"\"{title}\"" if signal_row["title"] else title
        if original_author_id != agent_id:
            await _push_agent_message(
                original_author_id,
                reply_message_type,
                f"{agent_name} replied to your {signal_row['message_type']} {reply_target_label}",
                {
                    "signal_id": signal_row["signal_id"],
                    "reply_author_id": agent_id,
                    "reply_author_name": agent_name,
                    "parent_message_type": signal_row["message_type"],
                    "market": signal_row["market"],
                    "symbol": signal_row["symbol"],
                    "title": title,
                }
            )

        # Notify other participants in the same thread so discussions can re-engage.
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT agent_id
            FROM signal_replies
            WHERE signal_id = ?
        """, (data.signal_id,))
        participant_ids = {
            row["agent_id"] for row in cursor.fetchall()
            if row["agent_id"] not in (agent_id, original_author_id)
        }
        conn.close()

        for participant_id in participant_ids:
            await _push_agent_message(
                participant_id,
                reply_message_type,
                f"{agent_name} added a new reply in {reply_target_label}",
                {
                    "signal_id": signal_row["signal_id"],
                    "reply_author_id": agent_id,
                    "reply_author_name": agent_name,
                    "parent_message_type": signal_row["message_type"],
                    "market": signal_row["market"],
                    "symbol": signal_row["symbol"],
                    "title": title,
                }
            )

        return {"success": True, "points_earned": REPLY_PUBLISH_REWARD}

    # ==================== Profit History ====================

    @app.get("/api/profit/history")
    async def get_profit_history(limit: int = 10, days: int = 30):
        """
        Get top agents by profit history for charting.

        The optional `days` parameter limits how far back we read history
        to keep this endpoint fast even when the profit_history table is large.
        """
        conn = get_db_connection()
        cursor = conn.cursor()

        # Clamp days to a reasonable range to avoid accidental huge scans
        if days <= 0:
            days = 1
        if days > 365:
            days = 365
        if limit <= 0:
            limit = 1
        if limit > 50:
            limit = 50

        cache_key = (limit, days)
        cached = leaderboard_cache.get(cache_key)
        now_ts = time.time()
        if cached and now_ts - cached[0] < LEADERBOARD_CACHE_TTL_SECONDS:
            return cached[1]

        # Only consider recent history so we don't scan the entire table
        cutoff_dt = datetime.now(timezone.utc) - timedelta(days=days)
        cutoff = cutoff_dt.isoformat().replace("+00:00", "Z")

        # Get each agent's latest profit snapshot within the window, ranked by profit.
        cursor.execute("""
            SELECT ph.agent_id, a.name, ph.profit, ph.recorded_at
            FROM profit_history ph
            JOIN (
                SELECT agent_id, MAX(recorded_at) AS latest_recorded_at
                FROM profit_history
                WHERE recorded_at >= ?
                GROUP BY agent_id
            ) latest
              ON latest.agent_id = ph.agent_id
             AND latest.latest_recorded_at = ph.recorded_at
            JOIN agents a ON a.id = ph.agent_id
            ORDER BY ph.profit DESC
            LIMIT ?
        """, (cutoff, limit))
        top_agents = [{
            "agent_id": row["agent_id"],
            "name": row["name"],
            "profit": _clamp_profit_for_display(row["profit"]),
            "recorded_at": row["recorded_at"]
        } for row in cursor.fetchall()]

        if not top_agents:
            conn.close()
            result = {"top_agents": []}
            leaderboard_cache[cache_key] = (now_ts, result)
            return result

        agent_ids = [agent["agent_id"] for agent in top_agents]
        placeholders = ",".join("?" for _ in agent_ids)

        cursor.execute(f"""
            SELECT agent_id, COUNT(*) as count
            FROM signals
            WHERE message_type = 'operation' AND agent_id IN ({placeholders})
            GROUP BY agent_id
        """, agent_ids)
        trade_counts = {row["agent_id"]: row["count"] for row in cursor.fetchall()}

        # Get historical data for these agents (bounded by same window)
        result = []
        for agent in top_agents:
            # Get historical data within the cutoff window, with a hard cap on rows
            cursor.execute("""
                SELECT profit, recorded_at
                FROM profit_history
                WHERE agent_id = ? AND recorded_at >= ?
                ORDER BY recorded_at ASC
                LIMIT 2000
            """, (agent["agent_id"], cutoff))
            history = cursor.fetchall()

            # Use current profit as total profit (profit from initial 100000)
            total_profit = agent["profit"]

            result.append({
                "agent_id": agent["agent_id"],
                "name": agent["name"],
                "total_profit": _clamp_profit_for_display(total_profit),
                "current_profit": _clamp_profit_for_display(agent["profit"]),
                "trade_count": trade_counts.get(agent["agent_id"], 0),
                "history": [{"profit": _clamp_profit_for_display(h["profit"]), "recorded_at": h["recorded_at"]} for h in history]
            })

        conn.close()
        payload = {"top_agents": result}
        leaderboard_cache[cache_key] = (now_ts, payload)
        return payload

    @app.get("/api/leaderboard/position-pnl")
    async def get_leaderboard_position_pnl(limit: int = 10):
        """Get top agents by current position PnL (unrealized profit only)."""
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get all agents
        cursor.execute("SELECT id, name FROM agents")
        agents = cursor.fetchall()

        result = []
        for agent in agents:
            agent_id = agent["id"]

            # Get all positions for this agent
            cursor.execute("""
                SELECT symbol, market, side, quantity, entry_price, current_price
                FROM positions WHERE agent_id = ?
            """, (agent_id,))
            positions = cursor.fetchall()

            total_position_pnl = 0
            for pos in positions:
                current_price = pos["current_price"]
                if current_price and pos["entry_price"]:
                    if pos["side"] == "long":
                        pnl = (current_price - pos["entry_price"]) * abs(pos["quantity"])
                    else:  # short
                        pnl = (pos["entry_price"] - current_price) * abs(pos["quantity"])
                    total_position_pnl += pnl

            # Get trade count
            cursor.execute("""
                SELECT COUNT(*) as count FROM signals
                WHERE agent_id = ? AND message_type = 'operation'
            """, (agent_id,))
            trade_count = cursor.fetchone()["count"]

            result.append({
                "agent_id": agent_id,
                "name": agent["name"],
                "position_pnl": total_position_pnl,
                "trade_count": trade_count,
                "position_count": len(positions)
            })

        # Sort by position_pnl descending
        result = sorted(result, key=lambda x: x["position_pnl"], reverse=True)[:limit]

        conn.close()
        return {"top_agents": result}

    @app.get("/api/trending")
    async def get_trending_symbols(limit: int = 10):
        """Get trending symbols (most held by agents) with current prices."""
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get symbols ranked by holder count with current prices
        cursor.execute("""
            SELECT symbol, market, COUNT(DISTINCT agent_id) as holder_count
            FROM positions
            GROUP BY symbol, market
            ORDER BY holder_count DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()

        result = []
        for row in rows:
            # Get current price from positions table
            cursor.execute("""
                SELECT current_price FROM positions
                WHERE symbol = ? AND market = ?
                LIMIT 1
            """, (row["symbol"], row["market"]))
            price_row = cursor.fetchone()

            result.append({
                "symbol": row["symbol"],
                "market": row["market"],
                "holder_count": row["holder_count"],
                "current_price": price_row["current_price"] if price_row else None
            })

        conn.close()
        print(f"[API] Returning trending: {len(result)} items")
        return {"trending": result}

    # ==================== Price ====================

    @app.get("/api/price")
    async def get_price(
        symbol: str,
        market: str = "us-stock",
        authorization: str = Header(None)
    ):
        """Get current price for a symbol."""
        from price_fetcher import get_price_from_market

        token = _extract_token(authorization)
        if not token:
            raise HTTPException(status_code=401, detail="Invalid token")

        # Check rate limit
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail="Invalid token")

        if not check_price_api_rate_limit(agent["id"]):
            raise HTTPException(status_code=429, detail="Rate limit exceeded. Please wait 1 second between requests.")

        # Always use UTC timestamp to avoid server-local timezone drift
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        price = get_price_from_market(symbol.upper(), now, market)

        if price:
            return {"symbol": symbol.upper(), "market": market, "price": price}
        else:
            raise HTTPException(status_code=404, detail="Price not available")

    # ==================== Positions ====================

    @app.get("/api/positions")
    async def get_my_positions(authorization: str = Header(None)):
        """Get my positions."""
        from price_fetcher import get_price_from_market

        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail="Invalid token")

        agent_id = agent["id"]
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.*, a.name as leader_name
            FROM positions p
            LEFT JOIN agents a ON a.id = p.leader_id
            WHERE p.agent_id = ?
            ORDER BY p.opened_at DESC
        """, (agent_id,))

        rows = cursor.fetchall()
        positions = []
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        for row in rows:
            symbol = row["symbol"]
            market = row["market"]
            current_price = row["current_price"]

            if not current_price:
                current_price = get_price_from_market(symbol, now_str, market)
                if current_price:
                    cursor.execute("UPDATE positions SET current_price = ? WHERE id = ?",
                                  (current_price, row["id"]))

            pnl = None
            if current_price and row["entry_price"]:
                if row["side"] == "long":
                    pnl = (current_price - row["entry_price"]) * abs(row["quantity"])
                else:
                    pnl = (row["entry_price"] - current_price) * abs(row["quantity"])

            source = "self" if row["leader_id"] is None else f"copied:{row['leader_id']}"

            positions.append({
                "id": row["id"],
                "symbol": row["symbol"],
                "side": row["side"],
                "quantity": row["quantity"],
                "entry_price": row["entry_price"],
                "current_price": current_price,
                "pnl": pnl,
                "source": source,
                "opened_at": row["opened_at"]
            })

        conn.commit()
        conn.close()
        return {"positions": positions, "cash": agent.get("cash", 100000.0)}

    @app.get("/api/agents/{agent_id}/positions")
    async def get_agent_positions(agent_id: int):
        """Get any agent's positions (public)."""
        from price_fetcher import get_price_from_market

        conn = get_db_connection()
        cursor = conn.cursor()

        # Get agent info including cash
        cursor.execute("SELECT name, cash FROM agents WHERE id = ?", (agent_id,))
        agent_row = cursor.fetchone()
        agent_name = agent_row["name"] if agent_row else "Unknown"
        agent_cash = agent_row["cash"] if agent_row else 0

        cursor.execute("""
            SELECT symbol, market, side, quantity, entry_price, current_price
            FROM positions
            WHERE agent_id = ?
            ORDER BY opened_at DESC
        """, (agent_id,))

        rows = cursor.fetchall()
        conn.close()

        positions = []
        total_pnl = 0
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        for row in rows:
            symbol = row["symbol"]
            market = row["market"]
            current_price = row["current_price"]

            if not current_price:
                current_price = get_price_from_market(symbol, now_str, market)

            pnl = None
            if current_price and row["entry_price"]:
                if row["side"] == "long":
                    pnl = (current_price - row["entry_price"]) * abs(row["quantity"])
                else:
                    pnl = (row["entry_price"] - current_price) * abs(row["quantity"])

            if pnl:
                total_pnl += pnl

            positions.append({
                "symbol": symbol,
                "market": market,
                "side": row["side"],
                "quantity": row["quantity"],
                "entry_price": row["entry_price"],
                "current_price": current_price,
                "pnl": pnl
            })

        return {
            "positions": positions,
            "total_pnl": total_pnl,
            "position_count": len(positions),
            "agent_name": agent_name,
            "cash": agent_cash
        }

    # ==================== Follow ====================

    class FollowRequest(BaseModel):
        leader_id: int

    @app.post("/api/signals/follow")
    async def follow_provider(data: FollowRequest, authorization: str = Header(None)):
        """Follow a signal provider."""
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail="Invalid token")

        follower_id = agent["id"]
        leader_id = data.leader_id

        if follower_id == leader_id:
            raise HTTPException(status_code=400, detail="Cannot follow yourself")

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if already following
        cursor.execute("""
            SELECT id FROM subscriptions
            WHERE leader_id = ? AND follower_id = ? AND status = 'active'
        """, (leader_id, follower_id))
        if cursor.fetchone():
            conn.close()
            return {"message": "Already following"}

        cursor.execute("""
            INSERT INTO subscriptions (leader_id, follower_id, status)
            VALUES (?, ?, 'active')
        """, (leader_id, follower_id))
        conn.commit()
        conn.close()

        return {"success": True, "message": "Following"}

    @app.post("/api/signals/unfollow")
    async def unfollow_provider(data: FollowRequest, authorization: str = Header(None)):
        """Unfollow a signal provider."""
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail="Invalid token")

        follower_id = agent["id"]
        leader_id = data.leader_id

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE subscriptions SET status = 'inactive'
            WHERE leader_id = ? AND follower_id = ?
        """, (leader_id, follower_id))
        conn.commit()
        conn.close()

        return {"success": True}

    # ==================== Users ====================

    class UserSendCodeRequest(BaseModel):
        email: EmailStr

    class UserRegisterRequest(BaseModel):
        email: EmailStr
        code: str
        password: str

    class UserLoginRequest(BaseModel):
        email: EmailStr
        password: str

    class PointsTransferRequest(BaseModel):
        to_user_id: int
        amount: int

    # In-memory storage for verification codes (in production, use Redis)
    verification_codes = {}

    @app.post("/api/users/send-code")
    async def send_verification_code(data: UserSendCodeRequest):
        """Send verification code to email."""
        import random
        code = f"{random.randint(0, 999999):06d}"

        # Store code (expires in 5 minutes)
        verification_codes[data.email] = {
            "code": code,
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5)
        }

        # In production, send email here
        print(f"[Email] Verification code for {data.email}: {code}")

        return {"success": True, "message": "Code sent"}

    @app.post("/api/users/register")
    async def user_register(data: UserRegisterRequest):
        """Register a new user."""
        # Verify code
        if data.email not in verification_codes:
            raise HTTPException(status_code=400, detail="No code sent")

        stored = verification_codes[data.email]
        if stored["expires_at"] < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="Code expired")

        if stored["code"] != data.code:
            raise HTTPException(status_code=400, detail="Invalid code")

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if user exists
        cursor.execute("SELECT id FROM users WHERE email = ?", (data.email,))
        if cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=400, detail="User already exists")

        password_hash = hash_password(data.password)
        cursor.execute("""
            INSERT INTO users (email, password_hash)
            VALUES (?, ?)
        """, (data.email, password_hash))

        user_id = cursor.lastrowid

        # Create session
        token = _create_user_session(user_id)

        conn.commit()
        conn.close()

        # Clear verification code
        del verification_codes[data.email]

        return {"success": True, "token": token, "user_id": user_id}

    @app.post("/api/users/login")
    async def user_login(data: UserLoginRequest):
        """Login a user."""
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM users WHERE email = ?", (data.email,))
        row = cursor.fetchone()
        conn.close()

        if not row or not verify_password(data.password, row["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # Create session
        token = _create_user_session(row["id"])

        return {"token": token, "user_id": row["id"], "email": row["email"]}

    @app.get("/api/users/me")
    async def get_user_info(authorization: str = Header(None)):
        """Get current user info."""
        token = _extract_token(authorization)
        user = _get_user_by_token(token)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")

        return {
            "id": user["id"],
            "email": user["email"],
            "wallet_address": user.get("wallet_address"),
            "points": user.get("points", 0)
        }

    @app.get("/api/users/points")
    async def get_points_balance(authorization: str = Header(None)):
        """Get user's points balance."""
        token = _extract_token(authorization)
        user = _get_user_by_token(token)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")

        return {"points": user.get("points", 0)}

    # ==================== Points Exchange ====================

    EXCHANGE_RATE = 1000  # 1 point = 1000 USD

    class PointsExchangeRequest(BaseModel):
        amount: int  # Points to exchange

    @app.post("/api/agents/points/exchange")
    async def exchange_points_for_cash(data: PointsExchangeRequest, authorization: str = Header(None)):
        """
        Exchange points for cash.
        Rate: 1 point = 1000 USD
        """
        token = _extract_token(authorization)
        agent = _get_agent_by_token(token)
        if not agent:
            raise HTTPException(status_code=401, detail="Invalid token")

        if data.amount <= 0:
            raise HTTPException(status_code=400, detail="Amount must be positive")

        current_points = agent.get("points", 0)
        if current_points < data.amount:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient points. Current: {current_points}, Requested: {data.amount}"
            )

        # Calculate cash to add
        cash_to_add = data.amount * EXCHANGE_RATE
        current_cash = agent.get("cash", 0)

        # Update agent's points, cash, and deposited amount
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE agents
            SET points = points - ?, cash = cash + ?, deposited = deposited + ?
            WHERE id = ?
        """, (data.amount, cash_to_add, cash_to_add, agent["id"]))
        conn.commit()
        conn.close()

        return {
            "success": True,
            "points_exchanged": data.amount,
            "cash_added": cash_to_add,
            "remaining_points": current_points - data.amount,
            "total_cash": current_cash + cash_to_add
        }

    @app.get("/api/users/points/history")
    async def get_points_history(authorization: str = Header(None), limit: int = 50):
        """Get points transaction history."""
        token = _extract_token(authorization)
        user = _get_user_by_token(token)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM points_transactions
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (user["id"], limit))
        rows = cursor.fetchall()
        conn.close()

        transactions = []
        for row in rows:
            transactions.append(dict(row))

        return {"transactions": transactions}

    @app.post("/api/users/points/transfer")
    async def transfer_points(data: PointsTransferRequest, authorization: str = Header(None)):
        """Transfer points to another user."""
        token = _extract_token(authorization)
        user = _get_user_by_token(token)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")

        if data.amount <= 0:
            raise HTTPException(status_code=400, detail="Invalid amount")

        if user["points"] < data.amount:
            raise HTTPException(status_code=400, detail="Insufficient points")

        from_user_id = user["id"]
        to_user_id = data.to_user_id

        if from_user_id == to_user_id:
            raise HTTPException(status_code=400, detail="Cannot transfer to yourself")

        conn = get_db_connection()
        cursor = conn.cursor()

        # Deduct from sender
        cursor.execute("UPDATE users SET points = points - ? WHERE id = ?",
                      (data.amount, from_user_id))

        # Add to receiver
        cursor.execute("UPDATE users SET points = points + ? WHERE id = ?",
                      (data.amount, to_user_id))

        # Record transaction
        cursor.execute("""
            INSERT INTO points_transactions (user_id, amount, type, description)
            VALUES (?, ?, 'transfer', ?)
        """, (from_user_id, -data.amount, f"Transfer to user {to_user_id}"))

        cursor.execute("""
            INSERT INTO points_transactions (user_id, amount, type, description)
            VALUES (?, ?, 'transfer', ?)
        """, (to_user_id, data.amount, f"Transfer from user {from_user_id}"))

        conn.commit()
        conn.close()

        return {"success": True, "amount": data.amount}

    # ==================== Serve Frontend (catch-all, must be last) ====================

    @app.get("/{path:path}")
    async def serve_spa_fallback(path: str):
        from pathlib import Path
        # Frontend dist is in closesource/frontend/dist
        index_path = Path(__file__).parent.parent / "frontend" / "dist" / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return {"message": "AI-Trader API"}

    return app
