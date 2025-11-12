# 🚀 JWT Authentication - Quick Reference

## Start Services

```bash
# Start all MCP services (including auth)
cd agent_tools
python start_mcp_services.py

# Or start auth service standalone
python -m auth.auth_service
```

## Test Authentication

```bash
# Health check
curl http://localhost:8004/

# Login (default admin)
curl -X POST http://localhost:8004/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# Register new user
curl -X POST http://localhost:8004/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"newuser","password":"pass123","email":"user@example.com"}'

# Get user info (requires token)
TOKEN="your-access-token-here"
curl http://localhost:8004/auth/me \
  -H "Authorization: Bearer $TOKEN"

# Verify token
curl -X POST http://localhost:8004/auth/verify \
  -H "Authorization: Bearer $TOKEN"

# Refresh token
curl -X POST http://localhost:8004/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"your-refresh-token-here"}'
```

## Python Example

```python
import requests

# Login
response = requests.post(
    "http://localhost:8004/auth/login",
    json={"username": "admin", "password": "admin123"}
)
tokens = response.json()
access_token = tokens["access_token"]

# Use token for authenticated requests
headers = {"Authorization": f"Bearer {access_token}"}
user = requests.get("http://localhost:8004/auth/me", headers=headers)
print(user.json())
```

## Run Tests

```bash
# Run all authentication tests
pytest tests/test_jwt_auth.py -v

# Run all tests
pytest tests/ -v
```

## Configuration

Edit `.env` file:

```bash
JWT_SECRET_KEY="your-secret-key-here"
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
AUTH_HTTP_PORT=8004
```

## Default Credentials

- Username: `admin`
- Password: `admin123`
- ⚠️ **Change in production!**

## API Documentation

- Swagger UI: http://localhost:8004/docs
- ReDoc: http://localhost:8004/redoc

## File Structure

```
auth/
├── jwt_utils.py          # JWT token operations
├── user_manager.py       # User management
├── auth_service.py       # FastAPI service
├── middleware.py         # Auth middleware
└── README.md            # Full documentation

tests/
├── test_jwt_auth.py      # Unit tests
└── test_auth_api.py      # API tests

JWT_AUTHENTICATION_GUIDE.md  # Complete setup guide
```

## Protecting Your Services

```python
from fastapi import Depends
from auth.middleware import verify_jwt_token

@app.get("/protected")
async def protected_route(user = Depends(verify_jwt_token)):
    return {"message": f"Hello {user['sub']}!"}
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Service won't start | Check port 8004 is available |
| "Invalid token" error | Token expired, use refresh token |
| Tests fail | Run `pip install -r requirements.txt` |
| Import errors | Run from project root: `python -m auth.auth_service` |

## Test Results

✅ **12/12 Unit Tests PASSED**
- JWT token creation ✓
- Token verification ✓
- Password hashing ✓
- User management ✓

✅ **Integration Tests PASSED**
- Login ✓
- Registration ✓
- Token verification ✓
- Protected endpoints ✓

## Quick Links

- Full Guide: `JWT_AUTHENTICATION_GUIDE.md`
- Auth README: `auth/README.md`
- API Docs: http://localhost:8004/docs
