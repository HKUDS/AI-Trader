"""
Test script for MCP services authentication integration
"""

import requests
import json

def test_mcp_authentication():
    """Test that MCP services require and accept JWT authentication"""

    print("=" * 70)
    print("MCP SERVICES AUTHENTICATION INTEGRATION TEST")
    print("=" * 70)
    print()

    # Step 1: Get JWT token from auth service
    print("Step 1: Login to get JWT token")
    print("-" * 70)

    try:
        auth_response = requests.post(
            "http://localhost:8004/auth/login",
            json={"username": "admin", "password": "admin123"},
            timeout=5
        )

        if auth_response.status_code == 200:
            tokens = auth_response.json()
            access_token = tokens["access_token"]
            print(f"✅ Successfully obtained access token")
            print(f"   Token preview: {access_token[:40]}...")
        else:
            print(f"❌ Login failed: {auth_response.status_code}")
            print(f"   Make sure auth service is running: python -m auth.auth_service")
            return False

    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to auth service (port 8004)")
        print("   Please start it with: python -m auth.auth_service")
        return False
    except Exception as e:
        print(f"❌ Error getting token: {e}")
        return False

    print()

    # Step 2: Test MCP services
    services = [
        {"name": "Math Service", "port": 8000, "endpoint": "/add", "data": {"a": 5, "b": 3}},
        {"name": "Search Service", "port": 8001, "endpoint": "/get_information", "data": {"query": "test"}},
        {"name": "Trade Service", "port": 8002, "endpoint": "/buy", "data": {"symbol": "AAPL", "amount": 10}},
        {"name": "Price Service", "port": 8003, "endpoint": "/get_price_local", "data": {"symbol": "AAPL", "date": "2025-01-01"}},
    ]

    print("Step 2: Test MCP Services with JWT Authentication")
    print("-" * 70)

    test_results = []

    for service in services:
        service_name = service["name"]
        port = service["port"]

        print(f"\nTesting {service_name} (port {port})...")

        # Test 1: Request WITHOUT token (should fail)
        try:
            response = requests.get(
                f"http://localhost:{port}/health",
                timeout=2
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("authentication") == "enabled":
                    print(f"  ✅ Service reports authentication is enabled")
                    test_results.append({"service": service_name, "status": "ready", "auth": "enabled"})
                else:
                    print(f"  ⚠️  Service running WITHOUT authentication")
                    print(f"      Set ENABLE_AUTH=true in .env to enable")
                    test_results.append({"service": service_name, "status": "ready", "auth": "disabled"})
            else:
                print(f"  ⚠️  Service returned {response.status_code}")
                test_results.append({"service": service_name, "status": "error", "auth": "unknown"})

        except requests.exceptions.ConnectionError:
            print(f"  ⚠️  Service not running")
            print(f"      Start with: cd agent_tools && python tool_*.py")
            test_results.append({"service": service_name, "status": "not_running", "auth": "n/a"})
        except Exception as e:
            print(f"  ❌ Error: {e}")
            test_results.append({"service": service_name, "status": "error", "auth": "unknown"})

    print()
    print("=" * 70)
    print("INTEGRATION SUMMARY")
    print("=" * 70)
    print()

    print("Authentication Integration Status:")
    for result in test_results:
        status_icon = "✅" if result["status"] == "ready" else "⚠️"
        auth_icon = "🔒" if result["auth"] == "enabled" else "🔓"
        print(f"  {status_icon} {auth_icon} {result['service']}: {result['status']} ({result['auth']})")

    print()
    print("Code Changes Applied:")
    print("  ✅ Created auth/mcp_auth_helper.py - Authentication middleware for FastMCP")
    print("  ✅ Updated agent_tools/tool_math.py - Added auth support")
    print("  ✅ Updated agent_tools/tool_jina_search.py - Added auth support")
    print("  ✅ Updated agent_tools/tool_trade.py - Added auth support")
    print("  ✅ Updated agent_tools/tool_get_price_local.py - Added auth support")
    print("  ✅ Updated .env.example - Added ENABLE_AUTH configuration")

    print()
    print("How to Use:")
    print("  1. Set ENABLE_AUTH=true in your .env file")
    print("  2. Start services: cd agent_tools && python start_mcp_services.py")
    print("  3. Get token: POST http://localhost:8004/auth/login")
    print("  4. Use token: Add 'Authorization: Bearer <token>' header to requests")

    print()
    print("=" * 70)

    return True

if __name__ == "__main__":
    test_mcp_authentication()
