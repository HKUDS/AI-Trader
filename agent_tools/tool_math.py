from fastmcp import FastMCP
import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Add parent directory to path for auth imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

mcp = FastMCP("Math")

@mcp.tool()
def add(a: float, b: float) -> float:
    """Add two numbers (supports int and float)"""
    return float(a) + float(b)

@mcp.tool()
def multiply(a: float, b: float) -> float:
    """Multiply two numbers (supports int and float)"""
    return float(a) * float(b)

if __name__ == "__main__":
    # Check if authentication should be enabled
    auth_enabled = os.getenv("ENABLE_AUTH", "true").lower() == "true"

    if auth_enabled:
        try:
            from auth.mcp_auth_helper import add_auth_to_mcp
            add_auth_to_mcp(mcp, "Math Service")
            print("✅ Math Service: Authentication enabled")
        except ImportError as e:
            print(f"⚠️  Warning: Could not enable authentication: {e}")
            print("   Running without authentication")
    else:
        print("ℹ️  Math Service: Running without authentication (set ENABLE_AUTH=true to enable)")

    port = int(os.getenv("MATH_HTTP_PORT", "8000"))
    mcp.run(transport="streamable-http", port=port)
