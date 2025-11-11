# JWT Authentication Implementation Guide

## 📋 Overview

This document provides a comprehensive guide for the JWT authentication system implemented in AI-Trader. The system provides secure token-based authentication for all MCP services.

## 🎯 What Was Implemented

### 1. Core Authentication Components

✅ **JWT Utilities** (`auth/jwt_utils.py`)
- Token creation (access & refresh tokens)
- Token verification and validation
- Configurable token expiration
- Built on PyJWT library

✅ **User Management** (`auth/user_manager.py`)
- User creation and storage (JSON-based)
- Password hashing with bcrypt
- User authentication
- Secure password verification

✅ **Authentication Service** (`auth/auth_service.py`)
- FastAPI-based REST API
- Login endpoint
- Registration endpoint
- Token refresh endpoint
- User profile endpoint
- Token verification endpoint

✅ **Middleware** (`auth/middleware.py`)
- JWT token verification middleware
- Request authentication decorator
- FastAPI middleware class for route protection

### 2. Configuration

✅ **Environment Variables** (`.env.example`)
```bash
JWT_SECRET_KEY="your-secret-key-change-in-production-use-long-random-string"
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
AUTH_HTTP_PORT=8004
```

### 3. Testing

✅ **Unit Tests** (`tests/test_jwt_auth.py`)
- JWT token creation tests
- Token verification tests
- User management tests
- Password hashing tests

✅ **API Integration Tests** (`tests/test_auth_api.py`)
- Registration endpoint tests
- Login endpoint tests
- Token refresh tests
- Protected route tests

### 4. Service Integration

✅ **Service Manager Update** (`agent_tools/start_mcp_services.py`)
- Added authentication service to MCP service manager
- Runs on port 8004 alongside other services

### 5. Dependencies

✅ **Updated requirements.txt**
- PyJWT==2.8.0 (JWT token handling)
- fastapi==0.109.2 (Web framework)
- uvicorn[standard]==0.27.1 (ASGI server)
- python-multipart==0.0.9 (Form data parsing)
- passlib[bcrypt]==1.7.4 (Password hashing)
- pytest==8.0.0 (Testing)
- httpx==0.26.0 (HTTP client for tests)

## 🚀 Getting Started

### Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 2: Configure Environment

Create/update your `.env` file:

```bash
cp .env.example .env
# Edit .env and set JWT_SECRET_KEY to a secure random value
```

Generate a secure secret key:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Step 3: Start Services

Start all MCP services including authentication:

```bash
cd agent_tools
python start_mcp_services.py
```

Or start authentication service standalone:

```bash
python auth/auth_service.py
```

### Step 4: Test Authentication

**Default credentials:**
- Username: `admin`
- Password: `admin123`

**Test with cURL:**
```bash
# Login
curl -X POST http://localhost:8004/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# Should return:
# {
#   "access_token": "eyJhbGc...",
#   "refresh_token": "eyJhbGc...",
#   "token_type": "bearer"
# }
```

**Test with Python:**
```python
import requests

# Login
response = requests.post(
    "http://localhost:8004/auth/login",
    json={"username": "admin", "password": "admin123"}
)
tokens = response.json()
print(f"Access Token: {tokens['access_token']}")

# Get user info
headers = {"Authorization": f"Bearer {tokens['access_token']}"}
user = requests.get("http://localhost:8004/auth/me", headers=headers)
print(user.json())
```

## 🔐 Protecting Your Services

### Example: Protecting an MCP Tool

Here's how to add authentication to an existing MCP tool:

```python
from fastmcp import FastMCP
from fastapi import Depends
from auth.middleware import verify_jwt_token

mcp = FastMCP("ProtectedTool")

@mcp.tool()
async def protected_operation(
    param: str,
    user = Depends(verify_jwt_token)
) -> dict:
    """
    This operation requires authentication
    """
    username = user.get("sub")
    return {
        "message": f"Hello {username}!",
        "result": f"Processed: {param}"
    }

if __name__ == "__main__":
    import os
    port = int(os.getenv("TOOL_PORT", "8005"))
    mcp.run(transport="streamable-http", port=port)
```

### Example: Adding Global Middleware

Protect all routes in a FastAPI app:

```python
from fastapi import FastAPI
from auth.middleware import AuthMiddleware

app = FastAPI()

# Add authentication middleware
app.add_middleware(
    AuthMiddleware,
    exclude_paths=["/", "/health", "/docs"]  # Public routes
)

@app.get("/protected")
async def protected_route():
    return {"message": "This requires authentication"}
```

## 📊 Authentication Flow

### Registration Flow
```
1. Client → POST /auth/register {username, password, email}
2. Server → Hash password with bcrypt
3. Server → Store user in JSON database
4. Server → Return user info (without password)
```

### Login Flow
```
1. Client → POST /auth/login {username, password}
2. Server → Verify credentials
3. Server → Create access_token (30 min expiry)
4. Server → Create refresh_token (7 day expiry)
5. Server → Return both tokens
```

### Making Authenticated Requests
```
1. Client → GET /protected-route
   Header: Authorization: Bearer <access_token>
2. Server → Extract token from header
3. Server → Verify token signature
4. Server → Check token expiration
5. Server → Process request with user context
```

### Token Refresh Flow
```
1. Client → POST /auth/refresh {refresh_token}
2. Server → Verify refresh token
3. Server → Check user still exists
4. Server → Create new access_token
5. Server → Create new refresh_token
6. Server → Return both tokens
```

## 🧪 Running Tests

### Run All Tests
```bash
pytest tests/ -v
```

### Run Authentication Tests Only
```bash
pytest tests/test_jwt_auth.py tests/test_auth_api.py -v
```

### Run with Coverage
```bash
pytest tests/ --cov=auth --cov-report=html
# View coverage report in htmlcov/index.html
```

### Expected Test Output
```
tests/test_jwt_auth.py::TestJWTUtils::test_create_access_token PASSED
tests/test_jwt_auth.py::TestJWTUtils::test_verify_access_token PASSED
tests/test_jwt_auth.py::TestUserManager::test_create_user PASSED
tests/test_auth_api.py::TestAuthEndpoints::test_login_success PASSED
...
=================== 20 passed in 2.34s ===================
```

## 🔒 Security Considerations

### Production Checklist

- [ ] Change `JWT_SECRET_KEY` to a secure random value
- [ ] Change default admin password
- [ ] Use HTTPS for all API communication
- [ ] Set appropriate token expiration times
- [ ] Implement rate limiting on auth endpoints
- [ ] Add logging for authentication events
- [ ] Consider implementing account lockout after failed attempts
- [ ] Use httpOnly cookies for token storage (web apps)
- [ ] Implement token blacklisting for logout
- [ ] Regular security audits

### Token Storage Best Practices

**✅ DO:**
- Store tokens in memory (client-side apps)
- Use httpOnly cookies (web apps)
- Clear tokens on logout
- Implement auto-refresh before expiration

**❌ DON'T:**
- Store tokens in localStorage (XSS vulnerable)
- Store tokens in sessionStorage
- Log tokens to console
- Commit tokens to version control
- Share tokens between users

## 📁 File Structure

```
AI-Trader/
├── auth/
│   ├── __init__.py
│   ├── jwt_utils.py          # JWT token operations
│   ├── user_manager.py       # User CRUD operations
│   ├── auth_service.py       # FastAPI authentication service
│   ├── middleware.py         # Authentication middleware
│   └── README.md            # Detailed auth documentation
├── tests/
│   ├── __init__.py
│   ├── test_jwt_auth.py      # Unit tests
│   └── test_auth_api.py      # API integration tests
├── data/
│   └── users.json           # User database (created automatically)
├── agent_tools/
│   └── start_mcp_services.py # Updated to include auth service
├── .env.example              # Updated with JWT config
├── requirements.txt          # Updated with auth dependencies
└── JWT_AUTHENTICATION_GUIDE.md  # This file
```

## 🐛 Troubleshooting

### Service Won't Start

**Problem:** Authentication service fails to start

**Solutions:**
1. Check if port 8004 is available:
   ```bash
   lsof -i :8004
   ```
2. Install missing dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Check logs in `logs/auth.log`

### Token Errors

**Problem:** "Invalid or expired token"

**Solutions:**
1. Token has expired (access tokens expire after 30 minutes)
   - Use refresh token to get new access token
2. Wrong secret key
   - Verify `JWT_SECRET_KEY` in `.env` matches
3. Token format incorrect
   - Use format: `Authorization: Bearer <token>`

### Authentication Fails

**Problem:** Login returns 401 Unauthorized

**Solutions:**
1. Verify credentials are correct
2. Check user exists in `data/users.json`
3. Password hashing working correctly
4. Check auth service logs

## 🔧 Advanced Configuration

### Custom Token Expiration

```python
from auth.jwt_utils import create_access_token
from datetime import timedelta

# Custom expiration
token = create_access_token(
    data={"sub": "username"},
    expires_delta=timedelta(hours=2)
)
```

### Custom User Database

Replace JSON storage with a proper database:

```python
# In auth/user_manager.py

# Replace load_users() and save_users() with:
import sqlite3

def load_users():
    conn = sqlite3.connect('users.db')
    # ... database logic
    return users

def save_users(users):
    conn = sqlite3.connect('users.db')
    # ... database logic
```

### Adding User Roles

Extend user data with roles:

```python
# In auth/user_manager.py
def create_user(username, password, email=None, role="user"):
    users[username] = {
        "password": get_password_hash(password),
        "email": email,
        "role": role  # Add role
    }

# In auth/jwt_utils.py
def create_access_token(data: Dict):
    to_encode["role"] = data.get("role", "user")
```

## 📚 API Reference

### Quick Reference

| Endpoint | Method | Auth Required | Description |
|----------|--------|---------------|-------------|
| `/` | GET | No | Health check |
| `/auth/register` | POST | No | Register new user |
| `/auth/login` | POST | No | Login and get tokens |
| `/auth/refresh` | POST | No | Refresh access token |
| `/auth/me` | GET | Yes | Get current user |
| `/auth/verify` | POST | Yes | Verify token validity |

Full API documentation available at: `http://localhost:8004/docs`

## 🎓 Next Steps

1. **Customize default users**: Change admin password or add more users
2. **Protect your services**: Add authentication to critical MCP tools
3. **Implement frontend**: Create a login UI for your web dashboard
4. **Add authorization**: Implement role-based access control (RBAC)
5. **Production deployment**: Follow security checklist above

## 📞 Support

For issues or questions:
1. Check this guide
2. Read `auth/README.md` for detailed documentation
3. Run tests to verify setup: `pytest tests/ -v`
4. Check service logs in `logs/auth.log`

## ✅ Summary

You now have a complete JWT authentication system with:
- ✅ Token-based authentication
- ✅ User registration and login
- ✅ Password hashing and security
- ✅ Token refresh mechanism
- ✅ Middleware for protecting routes
- ✅ Comprehensive tests
- ✅ Full documentation

Happy coding! 🚀
