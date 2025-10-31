import os

from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv()

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
    port = int(os.getenv("MATH_HTTP_PORT", "8000"))
    mcp.run(transport="streamable-http", port=port)
