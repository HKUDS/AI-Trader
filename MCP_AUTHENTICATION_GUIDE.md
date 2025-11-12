# 🔒 MCP Services Authentication Guide

This guide explains how to use JWT authentication with AI-Trader's MCP (Model Context Protocol) services.

## 📋 Overview

All MCP services (Math, Search, Trade, Price) now support JWT-based authentication. When enabled, these services require a valid JWT token in the `Authorization` header for all requests.

## 🚀 Quick Start

### 1. Enable Authentication

Set the `ENABLE_AUTH` flag in your `.env` file:

```bash
ENABLE_AUTH=true
JWT_SECRET_KEY="your-secret-key-here"
```

### 2. Start Services

```bash
cd agent_tools
python start_mcp_services.py
```

All services will start with authentication enabled:
- ✅ Math Service (port 8000)
- ✅ Search Service (port 8001)
- ✅ Trade Service (port 8002)
- ✅ Price Service (port 8003)
- ✅ Auth Service (port 8004)

### 3. Get Authentication Token

```bash
# Login to get token
curl -X POST http://localhost:8004/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
```

Response:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

### 4. Use Authenticated Services

Add the token to your requests:

```bash
TOKEN="your-access-token-here"

# Math Service Example
curl -X POST http://localhost:8000/tools/add \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"a": 5, "b": 3}'

# Price Service Example
curl -X POST http://localhost:8003/tools/get_price_local \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL", "date": "2025-01-15"}'
```

## 📚 Services Overview

### Math Service (Port 8000)

**Tools:**
- `add(a, b)` - Add two numbers
- `multiply(a, b)` - Multiply two numbers

**Authentication:** Required when ENABLE_AUTH=true

**Health Check:** `GET /health` (no auth required)

### Search Service (Port 8001)

**Tools:**
- `get_information(query)` - Search and scrape web content using Jina AI

**Authentication:** Required when ENABLE_AUTH=true

**Health Check:** `GET /health` (no auth required)

### Trade Service (Port 8002)

**Tools:**
- `buy(symbol, amount)` - Buy stocks
- `sell(symbol, amount)` - Sell stocks

**Authentication:** Required when ENABLE_AUTH=true

**Health Check:** `GET /health` (no auth required)

### Price Service (Port 8003)

**Tools:**
- `get_price_local(symbol, date)` - Get historical stock prices

**Authentication:** Required when ENABLE_AUTH=true

**Health Check:** `GET /health` (no auth required)

## 🔐 Authentication Flow

```
1. Client → POST /auth/login {username, password}
   ↓
2. Auth Service → Verify credentials
   ↓
3. Auth Service → Return access_token + refresh_token
   ↓
4. Client → MCP Service Request + Authorization: Bearer <token>
   ↓
5. MCP Service → Verify token
   ↓
6. MCP Service → Process request if valid
   ↓
7. MCP Service → Return result
```

## 🛠️ Development Mode (No Authentication)

To run services WITHOUT authentication (for development):

```bash
# In .env file
ENABLE_AUTH=false
```

Or set environment variable:

```bash
export ENABLE_AUTH=false
cd agent_tools
python start_mcp_services.py
```

Services will start without authentication:
```
ℹ️  Math Service: Running without authentication
ℹ️  Search Service: Running without authentication
ℹ️  Trade Service: Running without authentication
ℹ️  Price Service: Running without authentication
```

## 🐍 Python Client Example

```python
import requests

class AuthenticatedMCPClient:
    def __init__(self, username="admin", password="admin123"):
        self.auth_url = "http://localhost:8004/auth"
        self.access_token = None
        self.refresh_token = None
        self.login(username, password)

    def login(self, username, password):
        """Login and get tokens"""
        response = requests.post(
            f"{self.auth_url}/login",
            json={"username": username, "password": password}
        )
        response.raise_for_status()
        tokens = response.json()
        self.access_token = tokens["access_token"]
        self.refresh_token = tokens["refresh_token"]

    def get_headers(self):
        """Get headers with authentication"""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

    def call_tool(self, service_port, tool_name, params):
        """Call an MCP tool with authentication"""
        url = f"http://localhost:{service_port}/tools/{tool_name}"
        response = requests.post(
            url,
            headers=self.get_headers(),
            json=params
        )
        response.raise_for_status()
        return response.json()

# Usage example
client = AuthenticatedMCPClient()

# Call Math service
result = client.call_tool(8000, "add", {"a": 10, "b": 5})
print(f"10 + 5 = {result}")

# Call Price service
price = client.call_tool(8003, "get_price_local", {
    "symbol": "AAPL",
    "date": "2025-01-15"
})
print(f"AAPL price: {price}")
```

## 🔧 Configuration

### Environment Variables

```bash
# Enable/Disable authentication for MCP services
ENABLE_AUTH=true

# JWT configuration (used by auth service and MCP services)
JWT_SECRET_KEY="your-secret-key-here"
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Service ports
MATH_HTTP_PORT=8000
SEARCH_HTTP_PORT=8001
TRADE_HTTP_PORT=8002
GETPRICE_HTTP_PORT=8003
AUTH_HTTP_PORT=8004
```

### Service-Specific Configuration

Each service checks the `ENABLE_AUTH` environment variable on startup:
- If `ENABLE_AUTH=true`: Adds authentication middleware
- If `ENABLE_AUTH=false` or not set: Runs without authentication

## 🧪 Testing

### Test Authentication Integration

```bash
python test_mcp_auth_integration.py
```

This script tests:
- ✅ Auth service login
- ✅ Token generation
- ✅ MCP services authentication status

### Manual Testing

```bash
# 1. Start auth service
python -m auth.auth_service

# 2. Get token
TOKEN=$(curl -s -X POST http://localhost:8004/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' \
  | python -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

# 3. Test without token (should fail if auth is enabled)
curl -X POST http://localhost:8000/tools/add \
  -H "Content-Type: application/json" \
  -d '{"a": 5, "b": 3}'

# 4. Test with token (should succeed)
curl -X POST http://localhost:8000/tools/add \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"a": 5, "b": 3}'
```

## 🔒 Security Considerations

### Production Deployment

1. **Change Default Credentials**
   ```bash
   # Default admin password should be changed!
   # Create new user or update admin password
   ```

2. **Use Strong Secret Key**
   ```bash
   # Generate a secure random key
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

3. **Enable HTTPS**
   - Use reverse proxy (nginx, traefik)
   - Enable SSL/TLS certificates
   - Never send tokens over HTTP in production

4. **Configure Token Expiration**
   ```bash
   ACCESS_TOKEN_EXPIRE_MINUTES=15  # Shorter for production
   REFRESH_TOKEN_EXPIRE_DAYS=1     # Shorter for production
   ```

### Rate Limiting

Consider adding rate limiting to prevent abuse:
- Limit login attempts
- Limit API requests per user
- Implement IP-based throttling

## 📊 Implementation Details

### Authentication Middleware (mcp_auth_helper.py)

The `MCPAuthMiddleware` class handles:
- Token extraction from Authorization header
- Token verification using JWT
- Token expiration checking
- User context injection into request scope

### Service Integration

Each service uses the `add_auth_to_mcp()` helper:

```python
from auth.mcp_auth_helper import add_auth_to_mcp

mcp = FastMCP("MyService")

@mcp.tool()
def my_tool():
    return "result"

if __name__ == "__main__":
    if os.getenv("ENABLE_AUTH", "true").lower() == "true":
        add_auth_to_mcp(mcp, "MyService")

    mcp.run(transport="streamable-http", port=8000)
```

## 🐛 Troubleshooting

### "Invalid token" Error

**Problem:** Getting 401 Unauthorized with "Invalid token"

**Solutions:**
1. Check token hasn't expired (30-minute default)
2. Verify JWT_SECRET_KEY matches between auth and MCP services
3. Use access token, not refresh token
4. Check token format: `Authorization: Bearer <token>`

### Services Running Without Authentication

**Problem:** Services accept requests without tokens

**Solutions:**
1. Check `ENABLE_AUTH=true` in .env
2. Restart services after changing .env
3. Verify auth middleware is loaded (check service logs)

### "Module not found" Errors

**Problem:** Services fail to start with import errors

**Solutions:**
1. Ensure auth module is in Python path
2. Run services from project root
3. Check all dependencies are installed: `pip install -r requirements.txt`

## 📝 Migration Guide

### From Unauthenticated to Authenticated

**Step 1:** Update .env
```bash
echo "ENABLE_AUTH=true" >> .env
```

**Step 2:** Restart services
```bash
cd agent_tools
python start_mcp_services.py
```

**Step 3:** Update client code
```python
# Before (no auth)
response = requests.post("http://localhost:8000/tools/add", json={"a": 5, "b": 3})

# After (with auth)
token = get_auth_token()  # Get from auth service
headers = {"Authorization": f"Bearer {token}"}
response = requests.post("http://localhost:8000/tools/add", json={"a": 5, "b": 3}, headers=headers)
```

## 📚 Additional Resources

- [JWT Authentication Guide](JWT_AUTHENTICATION_GUIDE.md) - Complete JWT system documentation
- [Quick Start Guide](QUICK_START_AUTH.md) - Quick reference for authentication
- [Auth Service README](auth/README.md) - Auth service API documentation
- FastMCP Documentation - MCP protocol details

## ✅ Summary

- ✅ All MCP services support JWT authentication
- ✅ Toggle authentication with `ENABLE_AUTH` flag
- ✅ Centralized auth service on port 8004
- ✅ Token-based access control
- ✅ Health check endpoints remain public
- ✅ Easy integration for clients

For more information, see the complete [JWT Authentication Guide](JWT_AUTHENTICATION_GUIDE.md).
