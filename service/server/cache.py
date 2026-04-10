"""
Cache Module

Redis-backed cache helpers with graceful fallback when Redis is disabled or unavailable.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Optional

from config import REDIS_ENABLED, REDIS_PREFIX, REDIS_URL

try:
    import redis
except ImportError:  # pragma: no cover - optional until Redis is installed
    redis = None


_CONNECT_RETRY_INTERVAL_SECONDS = 10.0
_client_lock = threading.Lock()
_redis_client: Optional["redis.Redis"] = None
_last_connect_attempt_at = 0.0
_last_connect_error: Optional[str] = None


def _namespaced(key: str) -> str:
    cleaned = (key or "").strip()
    if not cleaned:
        raise ValueError("Cache key must not be empty")
    return f"{REDIS_PREFIX}:{cleaned}"


def redis_configured() -> bool:
    return REDIS_ENABLED and bool(REDIS_URL)


def get_redis_client() -> Optional["redis.Redis"]:
    global _redis_client, _last_connect_attempt_at, _last_connect_error

    if not redis_configured() or redis is None:
        return None

    if _redis_client is not None:
        return _redis_client

    now = time.time()
    if now - _last_connect_attempt_at < _CONNECT_RETRY_INTERVAL_SECONDS:
        return None

    with _client_lock:
        if _redis_client is not None:
            return _redis_client

        now = time.time()
        if now - _last_connect_attempt_at < _CONNECT_RETRY_INTERVAL_SECONDS:
            return None

        _last_connect_attempt_at = now
        try:
            client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
            client.ping()
            _redis_client = client
            _last_connect_error = None
            return _redis_client
        except Exception as exc:
            _redis_client = None
            _last_connect_error = str(exc)
            return None


def get_cache_status() -> dict[str, Any]:
    client = get_redis_client()
    return {
        "enabled": REDIS_ENABLED,
        "configured": bool(REDIS_URL),
        "available": client is not None,
        "prefix": REDIS_PREFIX,
        "client_installed": redis is not None,
        "last_error": _last_connect_error,
    }


def get_json(key: str) -> Optional[Any]:
    client = get_redis_client()
    if client is None:
        return None

    raw = client.get(_namespaced(key))
    if raw is None:
        return None

    try:
        return json.loads(raw)
    except Exception:
        return None


def set_json(key: str, value: Any, ttl_seconds: Optional[int] = None) -> bool:
    client = get_redis_client()
    if client is None:
        return False

    payload = json.dumps(value, separators=(",", ":"), default=str)
    namespaced_key = _namespaced(key)

    if ttl_seconds is not None and ttl_seconds > 0:
        return bool(client.set(namespaced_key, payload, ex=int(ttl_seconds)))
    return bool(client.set(namespaced_key, payload))


def delete(key: str) -> int:
    client = get_redis_client()
    if client is None:
        return 0
    return int(client.delete(_namespaced(key)))


def delete_pattern(pattern: str) -> int:
    client = get_redis_client()
    if client is None:
        return 0

    match_pattern = _namespaced(pattern)
    keys = list(client.scan_iter(match=match_pattern))
    if not keys:
        return 0
    return int(client.delete(*keys))


def acquire_lock(
    name: str,
    timeout_seconds: int = 30,
    blocking: bool = False,
    blocking_timeout: Optional[float] = None,
):
    client = get_redis_client()
    if client is None:
        return None

    return client.lock(
        _namespaced(f"lock:{name}"),
        timeout=timeout_seconds,
        blocking=blocking,
        blocking_timeout=blocking_timeout,
    )


def publish(channel: str, message: Any) -> int:
    client = get_redis_client()
    if client is None:
        return 0

    if not isinstance(message, str):
        message = json.dumps(message, separators=(",", ":"), default=str)
    return int(client.publish(_namespaced(f"pubsub:{channel}"), message))


def create_pubsub():
    client = get_redis_client()
    if client is None:
        return None
    return client.pubsub()
