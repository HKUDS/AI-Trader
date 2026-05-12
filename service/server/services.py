"""
Services Module

业务逻辑服务层
"""

import json
import secrets
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from database import get_db_connection, is_retryable_db_error


# ==================== Agent Services ====================

def _get_agent_by_token(token: str) -> Optional[Dict]:
    """Get agent by token."""
    if not token:
        return None
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM agents WHERE token = ?", (token,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def _get_agent_by_id(agent_id: Optional[int]) -> Optional[Dict]:
    """Get agent by numeric id."""
    if agent_id is None:
        return None
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM agents WHERE id = ?", (agent_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def _get_agent_by_name(name: str) -> Optional[Dict]:
    """Get agent by unique name.

    Prefer an exact match for backward compatibility with any legacy rows that
    may contain leading/trailing spaces, then fall back to the normalized name.
    """
    raw_name = name or ""
    normalized = raw_name.strip()
    if not normalized:
        return None
    conn = get_db_connection()
    cursor = conn.cursor()
    row = None
    for candidate in dict.fromkeys([raw_name, normalized]):
        cursor.execute("SELECT * FROM agents WHERE name = ?", (candidate,))
        row = cursor.fetchone()
        if row:
            break
    conn.close()
    return dict(row) if row else None


def _issue_agent_token(agent_id: int) -> str:
    """Rotate and return a fresh token for an agent."""
    token = secrets.token_urlsafe(32)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE agents SET token = ?, token_expires_at = NULL WHERE id = ?", (token, agent_id))
    conn.commit()
    conn.close()
    return token


def _get_or_issue_agent_token(agent: Dict) -> str:
    """Return the current agent API token, issuing one only for legacy empty rows."""
    token = (agent.get("token") or "").strip()
    if token:
        return token
    return _issue_agent_token(agent["id"])


def _get_user_by_token(token: str) -> Optional[Dict]:
    """Get user by token."""
    if not token:
        return None
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.*, t.token as session_token
        FROM users u
        JOIN user_tokens t ON t.user_id = u.id
        WHERE t.token = ? AND t.expires_at > datetime('now')
    """, (token,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def _create_user_session(user_id: int) -> str:
    """Create a new session for user."""
    import secrets
    from datetime import timedelta

    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat().replace("+00:00", "Z")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_tokens (user_id, token, expires_at)
        VALUES (?, ?, ?)
    """, (user_id, token, expires_at))
    conn.commit()
    conn.close()

    return token


def _add_agent_points(
    agent_id: int,
    points: int,
    reason: str = "reward",
    *,
    source_type: Optional[str] = None,
    source_id: Optional[Any] = None,
    experiment_key: Optional[str] = None,
    variant_key: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> bool:
    """Add points to an agent's account through the reward ledger."""
    if points <= 0:
        return False

    # Retry transient write conflicts on both SQLite and PostgreSQL.
    max_retries = 3
    for attempt in range(max_retries):
        try:
            from rewards import grant_agent_reward

            result = grant_agent_reward(
                agent_id,
                points,
                reason,
                source_type=source_type,
                source_id=source_id,
                experiment_key=experiment_key,
                variant_key=variant_key,
                metadata=metadata,
            )
            return bool(result.get("success"))
        except Exception as e:
            if is_retryable_db_error(e) and attempt < max_retries - 1:
                time.sleep(0.5 * (attempt + 1))
                continue
            print(f"[ERROR] Failed to add points to agent {agent_id}: {e}")
            return False
    return False


def _get_agent_points(agent_id: int) -> int:
    """Get agent's points balance."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT points FROM agents WHERE id = ?", (agent_id,))
    row = cursor.fetchone()
    conn.close()
    return row["points"] if row else 0


def _reserve_signal_id(cursor=None) -> int:
    """Reserve a unique signal ID using an autoincrement sequence table."""
    own_connection = False
    if cursor is None:
        conn = get_db_connection()
        cursor = conn.cursor()
        own_connection = True

    cursor.execute("INSERT INTO signal_sequence DEFAULT VALUES")
    signal_id = cursor.lastrowid

    if own_connection:
        conn.commit()
        conn.close()

    return signal_id


# ==================== Position Services ====================

def _update_position_from_signal(
    agent_id: int,
    symbol: str,
    market: str,
    action: str,
    quantity: float,
    price: float,
    executed_at: str,
    leader_id: int = None,
    cursor=None,
    token_id: Optional[str] = None,
    outcome: Optional[str] = None,
):
    """
    Update position based on trading signal.
    - buy: increase long position
    - sell: decrease/close long position
    - short: increase short position
    - cover: decrease/close short position
    leader_id: if set, this position is copied from another agent
    cursor: if provided, use this cursor instead of creating a new connection
    """
    # If no cursor provided, create a new connection
    own_connection = False
    if cursor is None:
        conn = get_db_connection()
        cursor = conn.cursor()
        own_connection = True

    # Get current position for this symbol
    query = """
        SELECT id, quantity, entry_price
        FROM positions
        WHERE agent_id = ? AND market = ?
    """
    params = [agent_id, market]
    if market == "polymarket":
        if not token_id:
            raise ValueError("Polymarket trades require token_id")
        query += " AND token_id = ?"
        params.append(token_id)
    else:
        query += " AND symbol = ?"
        params.append(symbol)
    cursor.execute(query, params)
    row = cursor.fetchone()

    current_qty = row["quantity"] if row else 0
    position_id = row["id"] if row else None

    action_lower = action.lower()
    if quantity is None:
        raise ValueError("Invalid quantity")
    if quantity <= 0:
        raise ValueError("Quantity must be positive")

    # Polymarket is spot-like paper trading: no naked shorts.
    if market == "polymarket" and action_lower in ("short", "cover"):
        raise ValueError("Polymarket does not support short/cover; use buy/sell of outcome tokens instead")

    if action_lower == "buy":
        # Increase long position
        if current_qty > 0:
            # Average in price
            new_qty = current_qty + quantity
            new_entry_price = ((current_qty * row["entry_price"]) + (quantity * price)) / new_qty
            cursor.execute("""
                UPDATE positions SET quantity = ?, entry_price = ?, opened_at = ?
                WHERE id = ?
            """, (new_qty, new_entry_price, executed_at, position_id))
            print(f"[Position] {symbol}: increased long position to {new_qty}")
        else:
            # Create new long position
            if leader_id:
                cursor.execute("""
                    INSERT INTO positions (agent_id, symbol, market, token_id, outcome, side, quantity, entry_price, opened_at, leader_id)
                    VALUES (?, ?, ?, ?, ?, 'long', ?, ?, ?, ?)
                """, (agent_id, symbol, market, token_id, outcome, quantity, price, executed_at, leader_id))
                print(f"[Position] {symbol}: created copied long position {quantity} from leader {leader_id}")
            else:
                cursor.execute("""
                    INSERT INTO positions (agent_id, symbol, market, token_id, outcome, side, quantity, entry_price, opened_at)
                    VALUES (?, ?, ?, ?, ?, 'long', ?, ?, ?)
                """, (agent_id, symbol, market, token_id, outcome, quantity, price, executed_at))
                print(f"[Position] {symbol}: created long position {quantity}")

    elif action_lower == "sell":
        # Decrease/close long position
        if current_qty <= 0:
            raise ValueError("No long position to sell")
        if quantity > current_qty:
            raise ValueError("Insufficient long position quantity")
        new_qty = current_qty - quantity
        if new_qty <= 0:
            # Close position
            cursor.execute("DELETE FROM positions WHERE id = ?", (position_id,))
            print(f"[Position] {symbol}: closed long position")
        else:
            # Partial close
            cursor.execute("""
                UPDATE positions SET quantity = ? WHERE id = ?
            """, (new_qty, position_id))
            print(f"[Position] {symbol}: decreased long position to {new_qty}")

    elif action_lower == "short":
        # Increase short position
        if current_qty < 0:
            # Add to existing short
            new_qty = current_qty - quantity
            current_short_qty = abs(current_qty)
            new_entry_price = (
                (current_short_qty * row["entry_price"]) + (quantity * price)
            ) / abs(new_qty)
            cursor.execute("""
                UPDATE positions SET quantity = ?, entry_price = ?, opened_at = ?
                WHERE id = ?
            """, (new_qty, new_entry_price, executed_at, position_id))
            print(f"[Position] {symbol}: increased short position to {new_qty}")
        else:
            # Create new short position (negative quantity for short)
            if leader_id:
                cursor.execute("""
                    INSERT INTO positions (agent_id, symbol, market, token_id, outcome, side, quantity, entry_price, opened_at, leader_id)
                    VALUES (?, ?, ?, ?, ?, 'short', ?, ?, ?, ?)
                """, (agent_id, symbol, market, token_id, outcome, -quantity, price, executed_at, leader_id))
                print(f"[Position] {symbol}: created copied short position {quantity} from leader {leader_id}")
            else:
                cursor.execute("""
                    INSERT INTO positions (agent_id, symbol, market, token_id, outcome, side, quantity, entry_price, opened_at)
                    VALUES (?, ?, ?, ?, ?, 'short', ?, ?, ?)
                """, (agent_id, symbol, market, token_id, outcome, -quantity, price, executed_at))
                print(f"[Position] {symbol}: created short position {quantity}")

    elif action_lower == "cover":
        # Decrease/close short position
        if current_qty >= 0:
            raise ValueError("No short position to cover")
        if quantity > abs(current_qty):
            raise ValueError("Insufficient short position quantity")
        new_qty = current_qty + quantity
        if new_qty >= 0:
            cursor.execute("DELETE FROM positions WHERE id = ?", (position_id,))
            print(f"[Position] {symbol}: closed short position")
        else:
            cursor.execute("""
                UPDATE positions SET quantity = ? WHERE id = ?
            """, (new_qty, position_id))
            print(f"[Position] {symbol}: decreased short position to {new_qty}")

    # Only commit and close if we created our own connection
    if own_connection:
        conn.commit()
        conn.close()


# ==================== Signal Services ====================

async def _broadcast_signal_to_followers(leader_id: int, signal_data: dict) -> int:
    """Broadcast signal to all followers."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT follower_id FROM subscriptions
        WHERE leader_id = ? AND status = 'active'
    """, (leader_id,))
    followers = cursor.fetchall()
    conn.close()

    # In a real implementation, this would send WebSocket notifications
    # For now, we just return the count
    return len(followers)
