"""
Utils Module

通用工具函数
"""

import hashlib
import secrets
import random
import time
import re
from typing import Optional, Dict, Any


def hash_password(password: str) -> str:
    """Hash a password using SHA256 with salt."""
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256((password + salt).encode()).hexdigest()
    return f"{salt}${hashed}"


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash."""
    try:
        salt, hashed = password_hash.split("$")
        return hashlib.sha256((password + salt).encode()).hexdigest() == hashed
    except:
        return False


def generate_verification_code() -> str:
    """Generate a 6-digit verification code."""
    return f"{random.randint(0, 999999):06d}"


def cleanup_expired_tokens():
    """Clean up expired user tokens."""
    from database import get_db_connection
    from datetime import datetime, timezone

    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    cursor.execute("DELETE FROM user_tokens WHERE expires_at < ?", (now,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    if deleted > 0:
        print(f"[Token Cleanup] Deleted {deleted} expired tokens")
    return deleted


def validate_address(address: str) -> str:
    """Validate and normalize an Ethereum address."""
    if not address:
        return ""
    # Remove 0x prefix if present
    if address.startswith("0x"):
        address = address[2:]
    # Ensure lowercase
    address = address.lower()
    # Validate hex
    if not re.match(r"^[0-9a-f]{40}$", address):
        return ""
    return f"0x{address}"


def _extract_token(authorization: str = None) -> Optional[str]:
    """Extract token from Authorization header."""
    if not authorization:
        return None
    if authorization.startswith("Bearer "):
        return authorization[7:]
    return authorization
