"""
Authentication Middleware
Provides middleware for protecting MCP services with JWT authentication
"""

from functools import wraps
from typing import Callable, Optional
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse

from auth.jwt_utils import verify_token


def extract_token_from_header(authorization: str) -> Optional[str]:
    """
    Extract JWT token from Authorization header

    Args:
        authorization: Authorization header value (e.g., "Bearer <token>")

    Returns:
        Token string if found, None otherwise
    """
    if not authorization:
        return None

    parts = authorization.split()

    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    return parts[1]


async def verify_jwt_token(request: Request) -> dict:
    """
    Verify JWT token from request

    Args:
        request: FastAPI request object

    Returns:
        Token payload if valid

    Raises:
        HTTPException: If token is missing or invalid
    """
    authorization = request.headers.get("Authorization")

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = extract_token_from_header(authorization)

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = verify_token(token, token_type="access")

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


def require_auth(func: Callable) -> Callable:
    """
    Decorator to require authentication for a function

    Usage:
        @require_auth
        def protected_function():
            return "This is protected"

    Args:
        func: Function to wrap

    Returns:
        Wrapped function that requires authentication
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Extract request from args (assumes first arg is Request)
        request = None
        for arg in args:
            if isinstance(arg, Request):
                request = arg
                break

        if not request:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Request object not found"
            )

        # Verify token
        await verify_jwt_token(request)

        # Call original function
        return await func(*args, **kwargs)

    return wrapper


class AuthMiddleware:
    """
    Authentication middleware for FastAPI applications

    Usage:
        app = FastAPI()
        app.add_middleware(AuthMiddleware, exclude_paths=["/health", "/docs"])
    """

    def __init__(self, app, exclude_paths: Optional[list] = None):
        self.app = app
        self.exclude_paths = exclude_paths or ["/", "/health", "/docs", "/openapi.json", "/redoc"]

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]

        # Check if path is excluded
        if path in self.exclude_paths:
            await self.app(scope, receive, send)
            return

        # Get headers
        headers = dict(scope.get("headers", []))
        authorization = headers.get(b"authorization", b"").decode("utf-8")

        if not authorization:
            response = JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Missing authorization header"},
                headers={"WWW-Authenticate": "Bearer"}
            )
            await response(scope, receive, send)
            return

        token = extract_token_from_header(authorization)

        if not token:
            response = JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Invalid authorization header format"},
                headers={"WWW-Authenticate": "Bearer"}
            )
            await response(scope, receive, send)
            return

        payload = verify_token(token, token_type="access")

        if payload is None:
            response = JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Invalid or expired token"},
                headers={"WWW-Authenticate": "Bearer"}
            )
            await response(scope, receive, send)
            return

        # Add user info to scope
        scope["user"] = payload

        await self.app(scope, receive, send)
