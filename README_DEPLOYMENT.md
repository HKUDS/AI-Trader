# 🚀 Automated Deployment System

## Overview

The AI-Trader authentication system now includes a complete automated deployment system that handles everything from dependency checking to service startup.

## 🎯 Quick Start

### Single Command Deployment

```bash
python3 deploy_auth_system.py
```

That's it! The script will:
1. Check your Python version
2. Identify and install missing dependencies
3. Create secure .env configuration
4. Verify port availability
5. Start all 5 services (Auth + 4 MCP services)
6. Run health checks
7. Test authentication flow

## 📁 Deployment Files

| File | Purpose |
|------|---------|
| `deploy_auth_system.py` | Main deployment script (Python) |
| `quick_deploy.sh` | Shell wrapper for easy execution |
| `DEPLOYMENT_GUIDE.md` | Complete deployment documentation |
| `README_DEPLOYMENT.md` | This file |

## 🛠️ Features

### Intelligent Dependency Management

The script automatically:
- ✅ Detects Python version (requires 3.8+)
- ✅ Checks all required packages
- ✅ Identifies missing or outdated dependencies
- ✅ Offers to install from requirements.txt
- ✅ Verifies installation success

### Secure Configuration

- ✅ Creates .env from .env.example
- ✅ Generates secure random JWT secret (32 bytes)
- ✅ Sets authentication mode (on/off)
- ✅ Preserves existing configuration

### Service Management

- ✅ Checks port availability (8000-8004)
- ✅ Starts all services in background
- ✅ Monitors service health
- ✅ Graceful shutdown on Ctrl+C

### Health Verification

- ✅ Checks each service's /health endpoint
- ✅ Verifies authentication status
- ✅ Tests login flow
- ✅ Tests authenticated requests

## 💻 Usage Examples

### Standard Deployment (With Authentication)

```bash
python3 deploy_auth_system.py
```

Output:
```
======================================================================
              AI-TRADER AUTHENTICATION SYSTEM DEPLOYMENT
======================================================================

[Step 1/7] Checking Python Version
✅ Python version: 3.11.14

[Step 2/7] Checking Dependencies
ℹ️  Checking dependencies...
  ✓ langchain: installed
  ✓ fastapi: installed
  ...
✅ All dependencies satisfied

[Step 3/7] Setting Up Environment
✅ Created .env file with secure JWT secret key

[Step 4/7] Checking Port Availability
  ✓ Port 8004 (Authentication): available
  ✓ Port 8000 (Math): available
  ...

[Step 5/7] Initializing Default Users
ℹ️  Default admin user will be created: admin/admin123

[Step 6/7] Starting Services
✅ Authentication service started
✅ Math service started
✅ Search service started
✅ Trade service started
✅ Price service started

[Step 7/7] Running Health Checks
  ✓ auth: running (auth: enabled)
  ✓ math: running (auth: enabled)
  ...

✅ Health checks complete

======================================================================
                      DEPLOYMENT SUCCESSFUL!
======================================================================

✨ All services are running! ✨

Services:
  • Authentication: http://localhost:8004
  • Math Service: http://localhost:8000
  ...
```

### Check Dependencies Only

```bash
python3 deploy_auth_system.py --check-only
```

### Development Mode (No Authentication)

```bash
python3 deploy_auth_system.py --no-auth
```

### Skip Health Checks (Faster)

```bash
python3 deploy_auth_system.py --skip-tests
```

## 🔧 Command Line Options

```bash
python3 deploy_auth_system.py [OPTIONS]

Options:
  --check-only    Only check dependencies, don't install or start services
  --no-auth       Deploy without authentication (development mode)
  --skip-tests    Skip health checks after deployment
  --help          Show help message
```

## 📊 What Gets Installed

### Python Packages

From `requirements.txt`:

```
langchain==1.0.2
langchain-openai==1.0.1
langchain-mcp-adapters>=0.1.0
fastmcp==2.12.5           ← MCP protocol support
PyJWT==2.8.0              ← JWT authentication
fastapi==0.109.2          ← Web framework
uvicorn[standard]==0.27.1 ← ASGI server
python-multipart==0.0.9   ← Form data parsing
bcrypt==4.1.2             ← Password hashing
python-dotenv==1.0.0      ← Environment variables
pytest==8.0.0             ← Testing
httpx==0.26.0             ← HTTP client
```

### Environment Configuration

Creates `.env` with:

```bash
# Secure random JWT key
JWT_SECRET_KEY="<32-byte-random-string>"

# Authentication enabled by default
ENABLE_AUTH=true

# Token expiration
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Service ports
MATH_HTTP_PORT=8000
SEARCH_HTTP_PORT=8001
TRADE_HTTP_PORT=8002
GETPRICE_HTTP_PORT=8003
AUTH_HTTP_PORT=8004

# API keys (you need to add these)
JINA_API_KEY=""
ALPHAADVANTAGE_API_KEY=""
OPENAI_API_KEY=""
```

## 🎯 Post-Deployment

### 1. Add API Keys

Edit `.env` and add your API keys:

```bash
nano .env
# or
vim .env
```

### 2. Change Default Password

```bash
curl -X POST http://localhost:8004/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "youradmin",
    "password": "YourSecurePassword123!",
    "email": "admin@yourcompany.com"
  }'
```

### 3. Test the System

```bash
# Run integration tests
python test_mcp_auth_integration.py

# Or test manually
TOKEN=$(curl -s -X POST http://localhost:8004/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' \
  | python -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

curl -X POST http://localhost:8000/tools/add \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"a": 10, "b": 5}'
```

### 4. View API Documentation

Open in browser:
- http://localhost:8004/docs - Auth service API

## 🔍 Troubleshooting

### Script Won't Run

```bash
# Make sure it's executable
chmod +x deploy_auth_system.py

# Or run with python explicitly
python3 deploy_auth_system.py
```

### Dependencies Won't Install

```bash
# Upgrade pip first
python3 -m pip install --upgrade pip

# Try manual install
pip install -r requirements.txt

# Use virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Ports Already in Use

```bash
# Find what's using the port
lsof -i :8004

# Kill the process
kill -9 <PID>

# Or change ports in .env
```

### Services Won't Start

```bash
# Check if fastmcp is installed
python3 -c "import fastmcp; print(fastmcp.__version__)"

# Check Python version
python3 --version  # Must be 3.8+

# Try running services manually to see errors
python -m auth.auth_service
cd agent_tools && python tool_math.py
```

## 📈 Advanced Usage

### Custom Installation

If you need more control:

```bash
# 1. Check what's needed
python3 deploy_auth_system.py --check-only

# 2. Install manually
pip install -r requirements.txt

# 3. Configure manually
cp .env.example .env
# Edit .env with your settings

# 4. Start services
cd agent_tools
python start_mcp_services.py
```

### Programmatic Usage

You can import and use the deployment classes:

```python
from deploy_auth_system import DependencyChecker, ServiceManager

# Check dependencies
checker = DependencyChecker()
if not checker.check_all_dependencies():
    checker.install_dependencies()

# Start services
manager = ServiceManager()
manager.start_all_services()
```

### Docker Deployment

For containerized deployment, see DEPLOYMENT_GUIDE.md for Docker Compose configuration.

## 🔐 Security Notes

The deployment script:
- ✅ Generates secure random JWT keys (32 bytes)
- ✅ Uses bcrypt for password hashing
- ✅ Enables authentication by default
- ✅ Creates local .env (not committed to git)
- ⚠️ Creates default admin user (you must change password!)

**Production checklist:**
- [ ] Change default admin password
- [ ] Update JWT_SECRET_KEY to production value
- [ ] Add real API keys
- [ ] Configure HTTPS/SSL
- [ ] Set up monitoring
- [ ] Review token expiration times

## 📚 Documentation

Complete documentation available:

1. **DEPLOYMENT_GUIDE.md** - Full deployment guide
2. **MCP_AUTHENTICATION_GUIDE.md** - MCP authentication usage
3. **JWT_AUTHENTICATION_GUIDE.md** - JWT system details
4. **QUICK_START_AUTH.md** - Quick reference

## ✅ Summary

The automated deployment system provides:

- 🚀 **One-command deployment** - Just run and go
- 🔍 **Dependency management** - Automatic detection and installation
- 🔐 **Secure setup** - Random JWT keys, password hashing
- 🏥 **Health monitoring** - Automated verification
- 📊 **Clear feedback** - Color-coded, informative output
- 🛡️ **Error handling** - Graceful failures with helpful messages
- 📖 **Comprehensive docs** - Multiple documentation files

**Get started now:**

```bash
python3 deploy_auth_system.py
```

That's all you need!
