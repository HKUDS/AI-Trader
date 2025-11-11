"""
Authentication Service
FastAPI service providing JWT authentication endpoints
"""

import os
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
from dotenv import load_dotenv

from auth.jwt_utils import (
    create_access_token,
    create_refresh_token,
    verify_token
)
from auth.user_manager import (
    authenticate_user,
    create_user,
    get_user,
    initialize_default_users
)

load_dotenv()

# Initialize FastAPI app
app = FastAPI(
    title="AI-Trader Authentication Service",
    description="JWT-based authentication for AI-Trader MCP services",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security scheme
security = HTTPBearer()


# Request/Response Models
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, description="Username")
    password: str = Field(..., min_length=1, description="Password")


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, description="Username (min 3 characters)")
    password: str = Field(..., min_length=6, description="Password (min 6 characters)")
    email: Optional[str] = Field(None, description="Email address")


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    username: str
    email: Optional[str] = None


# Authentication dependency
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """
    Dependency to get the current authenticated user from JWT token

    Args:
        credentials: HTTP Authorization credentials

    Returns:
        User payload from token

    Raises:
        HTTPException: If token is invalid or expired
    """
    token = credentials.credentials
    payload = verify_token(token, token_type="access")

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


# Endpoints
@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "service": "AI-Trader Authentication Service",
        "status": "running",
        "version": "1.0.0"
    }


@app.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest):
    """
    Register a new user

    Args:
        request: Registration request with username, password, and optional email

    Returns:
        User information (without password)

    Raises:
        HTTPException: If username already exists
    """
    success = create_user(
        username=request.username,
        password=request.password,
        email=request.email
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )

    return UserResponse(username=request.username, email=request.email)


@app.post("/auth/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """
    Login and receive JWT tokens

    Args:
        request: Login request with username and password

    Returns:
        Access token and refresh token

    Raises:
        HTTPException: If credentials are invalid
    """
    user = authenticate_user(request.username, request.password)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create tokens
    access_token = create_access_token(data={"sub": user["username"]})
    refresh_token = create_refresh_token(data={"sub": user["username"]})

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token
    )


@app.post("/auth/refresh", response_model=TokenResponse)
async def refresh(request: RefreshRequest):
    """
    Refresh access token using refresh token

    Args:
        request: Refresh request with refresh token

    Returns:
        New access token and refresh token

    Raises:
        HTTPException: If refresh token is invalid or expired
    """
    payload = verify_token(request.refresh_token, token_type="refresh")

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username = payload.get("sub")

    # Verify user still exists
    user = get_user(username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    # Create new tokens
    access_token = create_access_token(data={"sub": username})
    refresh_token = create_refresh_token(data={"sub": username})

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token
    )


@app.get("/auth/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    """
    Get current user information

    Args:
        current_user: Current authenticated user from token

    Returns:
        User information

    Raises:
        HTTPException: If user not found
    """
    username = current_user.get("sub")
    user = get_user(username)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return UserResponse(username=user["username"], email=user.get("email"))


@app.post("/auth/verify")
async def verify_token_endpoint(current_user: dict = Depends(get_current_user)):
    """
    Verify if a token is valid

    Args:
        current_user: Current authenticated user from token

    Returns:
        Verification status and user information
    """
    return {
        "valid": True,
        "username": current_user.get("sub")
    }


if __name__ == "__main__":
    import uvicorn

    # Initialize default users
    initialize_default_users()

    # Get port from environment
    port = int(os.getenv("AUTH_HTTP_PORT", "8004"))

    print(f"🚀 Starting Authentication Service on port {port}")
    print(f"📝 API Documentation: http://localhost:{port}/docs")

    uvicorn.run(app, host="0.0.0.0", port=port)
