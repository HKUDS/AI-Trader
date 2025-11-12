"""
MCP Authentication Helper
Provides authentication integration for FastMCP services
"""

import sys
import os

# Add parent directory to path to import auth modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from typing import Optional
import jwt
from datetime import datetime


class MCPAuthMiddleware:
    """
    Authentication middleware for FastMCP services
    Validates JWT tokens for all requests except health checks
    """

    def __init__(self, app, secret_key: str, exclude_paths: Optional[list] = None):
        """
        Initialize authentication middleware

        Args:
            app: ASGI application
            secret_key: JWT secret key for verification
            exclude_paths: List of paths to exclude from authentication
        """
        self.app = app
        self.secret_key = secret_key
        self.exclude_paths = exclude_paths or ["/health", "/", "/docs", "/openapi.json", "/redoc"]

    async def __call__(self, scope, receive, send):
        """Process requests with JWT authentication"""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]

        # Skip authentication for excluded paths
        if path in self.exclude_paths:
            await self.app(scope, receive, send)
            return

        # Get authorization header
        headers = dict(scope.get("headers", []))
        authorization = headers.get(b"authorization", b"").decode("utf-8")

        if not authorization:
            response = JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "error": "Missing authorization header",
                    "detail": "Please provide a valid JWT token in the Authorization header"
                },
                headers={"WWW-Authenticate": "Bearer"}
            )
            await response(scope, receive, send)
            return

        # Extract token
        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            response = JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "error": "Invalid authorization header format",
                    "detail": "Use format: Authorization: Bearer <token>"
                },
                headers={"WWW-Authenticate": "Bearer"}
            )
            await response(scope, receive, send)
            return

        token = parts[1]

        # Verify token
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])

            # Check token type
            if payload.get("type") != "access":
                response = JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={
                        "error": "Invalid token type",
                        "detail": "Please use an access token"
                    },
                    headers={"WWW-Authenticate": "Bearer"}
                )
                await response(scope, receive, send)
                return

            # Check expiration
            exp = payload.get("exp")
            if exp and datetime.utcnow().timestamp() > exp:
                response = JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={
                        "error": "Token expired",
                        "detail": "Please refresh your token"
                    },
                    headers={"WWW-Authenticate": "Bearer"}
                )
                await response(scope, receive, send)
                return

            # Add user info to scope
            scope["user"] = payload
            scope["username"] = payload.get("sub")

        except jwt.ExpiredSignatureError:
            response = JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "error": "Token expired",
                    "detail": "Please refresh your token"
                },
                headers={"WWW-Authenticate": "Bearer"}
            )
            await response(scope, receive, send)
            return

        except jwt.InvalidTokenError as e:
            response = JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "error": "Invalid token",
                    "detail": str(e)
                },
                headers={"WWW-Authenticate": "Bearer"}
            )
            await response(scope, receive, send)
            return

        # Continue with authenticated request
        await self.app(scope, receive, send)


def add_auth_to_mcp(mcp_app, service_name: str):
    """
    Add authentication middleware to a FastMCP application

    Args:
        mcp_app: FastMCP application instance
        service_name: Name of the service (for logging)

    Returns:
        FastMCP app with authentication middleware added

    Example:
        from fastmcp import FastMCP
        from auth.mcp_auth_helper import add_auth_to_mcp

        mcp = FastMCP("MyService")

        @mcp.tool()
        def my_tool():
            return "protected data"

        # Add authentication
        add_auth_to_mcp(mcp, "MyService")

        # Run service
        mcp.run(transport="streamable-http", port=8000)
    """
    from dotenv import load_dotenv
    load_dotenv()

    # Get JWT secret from environment
    secret_key = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")

    # Access the underlying FastAPI app
    # FastMCP wraps FastAPI, so we need to add middleware to the FastAPI instance
    if hasattr(mcp_app, '_app'):
        fastapi_app = mcp_app._app
    elif hasattr(mcp_app, 'app'):
        fastapi_app = mcp_app.app
    else:
        # Try to get the app during runtime
        print(f"⚠️  Warning: Could not access FastAPI app for {service_name}")
        return mcp_app

    # Add authentication middleware
    fastapi_app.add_middleware(
        MCPAuthMiddleware,
        secret_key=secret_key,
        exclude_paths=["/health", "/", "/docs", "/openapi.json", "/redoc"]
    )

    # Add health check endpoint
    @fastapi_app.get("/health")
    async def health_check():
        return {
            "service": service_name,
            "status": "running",
            "authentication": "enabled"
        }

    print(f"🔒 Authentication enabled for {service_name}")
    print(f"   Public endpoints: /health, /docs")
    print(f"   All MCP tools require JWT authentication")

    return mcp_app


def verify_token_for_tool(request: Request) -> dict:
    """
    Verify JWT token from request for use in tool functions

    Args:
        request: FastAPI request object

    Returns:
        User payload from token

    Raises:
        HTTPException: If token is invalid

    Example:
        from fastapi import Request, Depends
        from auth.mcp_auth_helper import verify_token_for_tool

        @mcp.tool()
        def protected_tool(request: Request = None):
            user = verify_token_for_tool(request)
            return f"Hello {user['sub']}!"
    """
    if not request:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Request object not provided"
        )

    # Get username from scope (set by middleware)
    username = getattr(request.scope, 'username', None)
    user = getattr(request.scope, 'user', None)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )

    return user
