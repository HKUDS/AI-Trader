"""
Utils Module

通用工具函数
"""

import hashlib
import secrets
import random
import time
import re
import bcrypt
from typing import Optional, Dict, Any


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode(), salt)
    return hashed.decode()


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash (supports bcrypt and legacy SHA256)."""
    if not password_hash:
        return False

    # Check for bcrypt hash
    if password_hash.startswith("$2b$") or password_hash.startswith("$2a$"):
        try:
            return bcrypt.checkpw(password.encode(), password_hash.encode())
        except Exception:
            return False

    # Fallback to legacy SHA256 salt$hash format
    try:
        if "$" in password_hash:
            salt, hashed = password_hash.split("$", 1)
            return hashlib.sha256((password + salt).encode()).hexdigest() == hashed
    except Exception:
        pass

    return False


def generate_verification_code() -> str:
    """Generate a 6-digit verification code."""
    return f"{random.randint(0, 999999):06d}"


def build_agent_token_recovery_challenge(
    agent_id: int,
    agent_name: str,
    wallet_address: str,
    nonce: str,
    expires_at: str,
) -> str:
    """Build a human-readable challenge message for wallet-signed token recovery."""
    return (
        "AI-Trader token recovery\n\n"
        f"Agent ID: {agent_id}\n"
        f"Agent Name: {agent_name}\n"
        f"Wallet: {wallet_address}\n"
        f"Nonce: {nonce}\n"
        f"Expires At: {expires_at}\n\n"
        "Sign this message to issue a new API token."
    )


def build_agent_password_reset_challenge(
    agent_id: int,
    agent_name: str,
    wallet_address: str,
    nonce: str,
    expires_at: str,
) -> str:
    """Build a human-readable challenge message for wallet-signed password reset."""
    return (
        "AI-Trader password reset\n\n"
        f"Agent ID: {agent_id}\n"
        f"Agent Name: {agent_name}\n"
        f"Wallet: {wallet_address}\n"
        f"Nonce: {nonce}\n"
        f"Expires At: {expires_at}\n\n"
        "Sign this message to reset your password."
    )


def recover_signed_address(message: str, signature: str) -> Optional[str]:
    """Recover an Ethereum address from a signed challenge."""
    if not message or not signature:
        return None

    try:
        from eth_account import Account
        from eth_account.messages import encode_defunct

        recovered = Account.recover_message(
            encode_defunct(text=message),
            signature=signature,
        )
    except Exception:
        return None

    return validate_address(recovered)


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
