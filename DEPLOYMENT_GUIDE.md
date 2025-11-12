# 🚀 AI-Trader Authentication System - Deployment Guide

This guide covers deploying the complete JWT authentication system for AI-Trader.

## 📋 Quick Start

### One-Command Deployment

```bash
python3 deploy_auth_system.py
```

Or use the shell wrapper:

```bash
./quick_deploy.sh
```

This will:
1. ✅ Check Python version (3.8+ required)
2. ✅ Check and install dependencies
3. ✅ Create .env file with secure JWT key
4. ✅ Check port availability
5. ✅ Initialize default admin user
6. ✅ Start all services (Auth + 4 MCP services)
7. ✅ Run health checks
8. ✅ Test authentication flow

## 🛠️ Deployment Options

### Check Dependencies Only

Check what's installed without making changes:

```bash
python3 deploy_auth_system.py --check-only
```

### Deploy Without Authentication (Development Mode)

Run services without requiring JWT tokens:

```bash
python3 deploy_auth_system.py --no-auth
```

### Skip Health Checks

Deploy faster by skipping post-deployment tests:

```bash
python3 deploy_auth_system.py --skip-tests
```

### Get Help

```bash
python3 deploy_auth_system.py --help
```

## 📦 What Gets Deployed

### Services Started

| Service | Port | Purpose |
|---------|------|---------|
| Authentication | 8004 | JWT token generation and validation |
| Math Service | 8000 | Mathematical operations |
| Search Service | 8001 | Web search via Jina AI |
| Trade Service | 8002 | Stock trading operations |
| Price Service | 8003 | Historical stock price data |

### Files Created/Modified

**Created:**
- `.env` - Environment configuration (with secure JWT key)

**Modified:**
- None (deployment doesn't modify existing files)

**Used:**
- `.env.example` - Template for environment variables
- `requirements.txt` - Python dependencies

## 🔧 Manual Deployment Steps

If you prefer to deploy manually or the automated script fails:

### Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

Required packages:
- `fastmcp==2.12.5` - MCP protocol support
- `PyJWT==2.8.0` - JWT token handling
- `fastapi==0.109.2` - Web framework
- `uvicorn==0.27.1` - ASGI server
- `bcrypt==4.1.2` - Password hashing
- `pytest==8.0.0` - Testing framework
- And others (see requirements.txt)

### Step 2: Create Environment File

```bash
cp .env.example .env
```

Edit `.env` and set:
```bash
# Generate secure key
JWT_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"

# Enable authentication
ENABLE_AUTH=true

# Add your API keys
JINA_API_KEY="your-jina-api-key"
# ... other keys
```

### Step 3: Start Services

```bash
cd agent_tools
python start_mcp_services.py
```

Or start individually:
```bash
# Terminal 1: Auth service
python -m auth.auth_service

# Terminal 2: Math service
cd agent_tools && python tool_math.py

# Terminal 3: Search service
cd agent_tools && python tool_jina_search.py

# Terminal 4: Trade service
cd agent_tools && python tool_trade.py

# Terminal 5: Price service
cd agent_tools && python tool_get_price_local.py
```

### Step 4: Test Deployment

```bash
# Test auth service
curl http://localhost:8004/health

# Login
curl -X POST http://localhost:8004/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# Get token and test MCP service
TOKEN="your-token-here"
curl -X POST http://localhost:8000/tools/add \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"a": 5, "b": 3}'
```

## 🔍 Troubleshooting

### "Module not found" Errors

**Problem:** Import errors when starting services

**Solution:**
```bash
# Reinstall dependencies
pip install -r requirements.txt --force-reinstall

# Or install specific missing package
pip install fastmcp
```

### Port Already in Use

**Problem:** Port 8000-8004 already taken

**Solution:**
```bash
# Find process using port
lsof -i :8004

# Kill process
kill -9 <PID>

# Or change port in .env
echo "AUTH_HTTP_PORT=9004" >> .env
```

### Authentication Not Working

**Problem:** Services accept requests without tokens

**Solution:**
```bash
# Check ENABLE_AUTH is set
grep ENABLE_AUTH .env

# Should show: ENABLE_AUTH=true

# Restart services after changing .env
```

### Dependencies Installation Fails

**Problem:** pip install fails

**Solution:**
```bash
# Upgrade pip first
python3 -m pip install --upgrade pip

# Try again
pip install -r requirements.txt

# Or use virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Services Won't Start

**Problem:** Services crash on startup

**Solution:**
```bash
# Check Python version (needs 3.8+)
python3 --version

# Check if .env file exists
ls -la .env

# Check logs
# Services output to stdout/stderr

# Try running directly to see errors
python -m auth.auth_service
```

## 📊 Verification Checklist

After deployment, verify:

- [ ] All 5 services respond to /health endpoint
- [ ] Login returns JWT tokens
- [ ] Authenticated requests work
- [ ] Unauthenticated requests are rejected (if auth enabled)
- [ ] .env file has secure JWT_SECRET_KEY
- [ ] Default admin password noted (change it!)

### Quick Verification

```bash
# Run integration test
python test_mcp_auth_integration.py
```

Expected output:
```
✅ Login successful
✅ Math Service: ready (enabled)
✅ Search Service: ready (enabled)
✅ Trade Service: ready (enabled)
✅ Price Service: ready (enabled)
```

## 🔐 Post-Deployment Security

### 1. Change Default Password

```bash
# Register new admin
curl -X POST http://localhost:8004/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "youradmin",
    "password": "SecurePassword123!",
    "email": "admin@yourcompany.com"
  }'
```

### 2. Secure JWT Key

```bash
# Generate strong key
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Update .env
echo "JWT_SECRET_KEY=<generated-key>" >> .env

# Restart services
```

### 3. Configure Token Expiration

Edit `.env`:
```bash
# Shorter expiration for production
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=1
```

### 4. Add API Keys

Edit `.env`:
```bash
JINA_API_KEY="your-real-api-key"
ALPHAADVANTAGE_API_KEY="your-real-api-key"
OPENAI_API_KEY="your-real-api-key"
```

### 5. Enable HTTPS

In production, use a reverse proxy (nginx/traefik) with SSL/TLS:

```nginx
server {
    listen 443 ssl;
    server_name api.yourdomain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location /auth {
        proxy_pass http://localhost:8004;
    }

    location /math {
        proxy_pass http://localhost:8000;
    }
    # ... other services
}
```

## 🐳 Docker Deployment (Alternative)

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  auth-service:
    build: .
    command: python -m auth.auth_service
    ports:
      - "8004:8004"
    environment:
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
      - ENABLE_AUTH=true
    volumes:
      - ./data:/app/data

  math-service:
    build: .
    command: python agent_tools/tool_math.py
    ports:
      - "8000:8000"
    environment:
      - ENABLE_AUTH=true
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}

  # ... other services
```

Deploy with:
```bash
docker-compose up -d
```

## 📈 Monitoring

### Check Service Status

```bash
# All services
curl http://localhost:8004/health
curl http://localhost:8000/health
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
```

### View Logs

```bash
# If running in background
tail -f logs/*.log

# If using docker
docker-compose logs -f
```

### Monitor Performance

```bash
# Check CPU/Memory usage
ps aux | grep python

# Check port connections
netstat -an | grep LISTEN | grep -E "800[0-4]"
```

## 🔄 Update/Maintenance

### Update Dependencies

```bash
# Backup current environment
cp requirements.txt requirements.txt.backup

# Update packages
pip install --upgrade -r requirements.txt

# Test
python test_mcp_auth_integration.py
```

### Backup User Data

```bash
# Backup user database
cp data/users.json data/users.json.backup

# Backup trading data
tar -czf backup-$(date +%Y%m%d).tar.gz data/
```

### Restart Services

```bash
# Stop (Ctrl+C if running in foreground)

# Or kill processes
pkill -f "auth.auth_service"
pkill -f "tool_math.py"
pkill -f "tool_jina_search.py"
pkill -f "tool_trade.py"
pkill -f "tool_get_price_local.py"

# Start again
python3 deploy_auth_system.py
```

## 🎓 Next Steps

1. **Change default admin password** ⚠️
2. **Add your API keys** to .env
3. **Review security settings** in documentation
4. **Set up monitoring** for production
5. **Configure HTTPS** via reverse proxy
6. **Test with your applications**
7. **Read full documentation**:
   - MCP_AUTHENTICATION_GUIDE.md
   - JWT_AUTHENTICATION_GUIDE.md
   - QUICK_START_AUTH.md

## 📞 Support

- 📖 Documentation: See markdown files in project root
- 🐛 Issues: https://github.com/DellGibson/AI-Trader/issues
- 🧪 Tests: Run `pytest tests/` for full test suite

## ✅ Deployment Complete!

Your AI-Trader authentication system is now deployed and ready to use!

**Access Points:**
- Auth API: http://localhost:8004/docs
- Services: Ports 8000-8003
- Credentials: admin/admin123 (change this!)

**Remember:**
- 🔐 Change default password
- 🔑 Add real API keys
- 🛡️ Use HTTPS in production
- 📊 Monitor service health
- 💾 Backup user data regularly
