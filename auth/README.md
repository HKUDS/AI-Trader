# JWT Authentication for AI-Trader

This directory contains the JWT (JSON Web Token) authentication system for the AI-Trader platform.

## 📁 Structure

```
auth/
├── __init__.py              # Package initialization
├── jwt_utils.py             # JWT token creation and verification
├── user_manager.py          # User management and password hashing
├── auth_service.py          # FastAPI authentication service
├── middleware.py            # Authentication middleware for protecting routes
└── README.md               # This file
```

## 🚀 Quick Start

### 1. Configure Environment Variables

Add these to your `.env` file:

```bash
# JWT Authentication Configuration
JWT_SECRET_KEY="your-secret-key-change-in-production-use-long-random-string"
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Authentication Service Port
AUTH_HTTP_PORT=8004
```

**Important**: Change `JWT_SECRET_KEY` to a long, random string in production!

### 2. Start the Authentication Service

The authentication service is automatically started with other MCP services:

```bash
cd agent_tools
python start_mcp_services.py
```

Or start it standalone:

```bash
python auth/auth_service.py
```

The service will be available at `http://localhost:8004`

### 3. API Documentation

Once the service is running, visit:
- Swagger UI: `http://localhost:8004/docs`
- ReDoc: `http://localhost:8004/redoc`

## 📚 API Endpoints

### Register a New User

```bash
POST /auth/register
Content-Type: application/json

{
  "username": "john_doe",
  "password": "securepassword123",
  "email": "john@example.com"
}
```

**Response:**
```json
{
  "username": "john_doe",
  "email": "john@example.com"
}
```

### Login

```bash
POST /auth/login
Content-Type: application/json

{
  "username": "john_doe",
  "password": "securepassword123"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

### Get Current User

```bash
GET /auth/me
Authorization: Bearer <access_token>
```

**Response:**
```json
{
  "username": "john_doe",
  "email": "john@example.com"
}
```

### Verify Token

```bash
POST /auth/verify
Authorization: Bearer <access_token>
```

**Response:**
```json
{
  "valid": true,
  "username": "john_doe"
}
```

### Refresh Token

```bash
POST /auth/refresh
Content-Type: application/json

{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

## 🔐 Using Authentication in Your Code

### Python Example

```python
import requests

# 1. Login
response = requests.post(
    "http://localhost:8004/auth/login",
    json={
        "username": "admin",
        "password": "admin123"
    }
)

tokens = response.json()
access_token = tokens["access_token"]

# 2. Make authenticated requests
headers = {"Authorization": f"Bearer {access_token}"}

response = requests.get(
    "http://localhost:8004/auth/me",
    headers=headers
)

print(response.json())
```

### JavaScript/Node.js Example

```javascript
// 1. Login
const loginResponse = await fetch('http://localhost:8004/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    username: 'admin',
    password: 'admin123'
  })
});

const { access_token } = await loginResponse.json();

// 2. Make authenticated requests
const userResponse = await fetch('http://localhost:8004/auth/me', {
  headers: { 'Authorization': `Bearer ${access_token}` }
});

const user = await userResponse.json();
console.log(user);
```

### cURL Example

```bash
# 1. Login
TOKEN=$(curl -X POST http://localhost:8004/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' \
  | jq -r '.access_token')

# 2. Make authenticated request
curl http://localhost:8004/auth/me \
  -H "Authorization: Bearer $TOKEN"
```

## 🛡️ Protecting Your Services

### Using Middleware

To protect your FastAPI/MCP services with authentication:

```python
from fastapi import FastAPI, Depends
from auth.middleware import verify_jwt_token

app = FastAPI()

@app.get("/protected")
async def protected_route(user = Depends(verify_jwt_token)):
    return {"message": f"Hello {user['sub']}!"}
```

### Using Decorator

```python
from fastapi import Request
from auth.middleware import require_auth

@require_auth
async def protected_function(request: Request):
    return {"message": "This is protected"}
```

### Using Middleware Class

```python
from fastapi import FastAPI
from auth.middleware import AuthMiddleware

app = FastAPI()

# Protect all routes except excluded paths
app.add_middleware(
    AuthMiddleware,
    exclude_paths=["/", "/health", "/docs", "/openapi.json"]
)
```

## 👤 User Management

### Default User

A default admin user is created automatically:
- **Username**: `admin`
- **Password**: `admin123`

**⚠️ Change this password in production!**

### Programmatic User Management

```python
from auth.user_manager import create_user, authenticate_user, get_user

# Create a new user
success = create_user(
    username="newuser",
    password="password123",
    email="user@example.com"
)

# Authenticate user
user = authenticate_user("newuser", "password123")
if user:
    print(f"Authenticated: {user['username']}")

# Get user info
user = get_user("newuser")
print(user)
```

## 🔧 JWT Utilities

### Creating Tokens

```python
from auth.jwt_utils import create_access_token, create_refresh_token

# Create access token
access_token = create_access_token(data={"sub": "username"})

# Create refresh token
refresh_token = create_refresh_token(data={"sub": "username"})
```

### Verifying Tokens

```python
from auth.jwt_utils import verify_token

# Verify access token
payload = verify_token(access_token, token_type="access")
if payload:
    print(f"User: {payload['sub']}")

# Verify refresh token
payload = verify_token(refresh_token, token_type="refresh")
```

## 🧪 Testing

Run the authentication tests:

```bash
# Run all auth tests
pytest tests/test_jwt_auth.py tests/test_auth_api.py -v

# Run specific test file
pytest tests/test_jwt_auth.py -v

# Run with coverage
pytest tests/ --cov=auth --cov-report=html
```

## 🔒 Security Best Practices

1. **Change the Secret Key**: Always use a strong, random secret key in production
   ```bash
   # Generate a secure random key
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. **Use HTTPS**: Always use HTTPS in production to prevent token interception

3. **Token Expiration**: Access tokens expire after 30 minutes by default. Use refresh tokens to get new access tokens.

4. **Store Tokens Securely**:
   - Never store tokens in localStorage (vulnerable to XSS)
   - Use httpOnly cookies or secure storage mechanisms
   - Never commit tokens to version control

5. **Validate Input**: All endpoints validate input using Pydantic models

6. **Password Hashing**: Passwords are hashed using bcrypt before storage

## 📊 Token Lifecycle

```
1. User logs in with credentials
   ↓
2. Server validates credentials
   ↓
3. Server creates access_token (30 min) + refresh_token (7 days)
   ↓
4. Client stores tokens securely
   ↓
5. Client uses access_token for API requests
   ↓
6. When access_token expires:
   - Client uses refresh_token to get new tokens
   - Repeat from step 3
   ↓
7. When refresh_token expires:
   - User must log in again
```

## 🐛 Troubleshooting

### "Invalid or expired token" Error

- Check if your token has expired (access tokens last 30 minutes)
- Use the refresh token to get a new access token
- Verify you're using the correct JWT_SECRET_KEY

### "Missing authorization header" Error

- Ensure you're sending the Authorization header: `Authorization: Bearer <token>`
- Check the header format is correct

### "Username already exists" Error

- The username is already taken
- Try a different username or use login instead

### Service Won't Start

- Check if port 8004 is already in use
- Verify all dependencies are installed: `pip install -r requirements.txt`
- Check the logs in `logs/auth.log`

## 📝 Configuration Reference

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `JWT_SECRET_KEY` | `your-secret-key-change-in-production` | Secret key for signing JWT tokens |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access token expiration time in minutes |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token expiration time in days |
| `AUTH_HTTP_PORT` | `8004` | Port for authentication service |

## 🤝 Contributing

When contributing to the authentication system:

1. Add tests for new features
2. Update this documentation
3. Follow security best practices
4. Never commit sensitive data

## 📄 License

This authentication system is part of the AI-Trader project and follows the same license.
