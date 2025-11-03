import os

from dotenv import load_dotenv
from fastmcp import FastMCP

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.general_tools import get_config_value
load_dotenv()

mcp = FastMCP("Math")


@mcp.tool()
def add(a: float, b: float) -> float:
    """Add two numbers (supports int and float)"""
    # log_file = get_config_value("LOG_FILE")
    # signature = get_config_value("SIGNATURE")
    # log_entry = {
    #     "signature": signature,
    #     "new_messages": [{"role": "tool:add", "content": f"{a} + {b} = {float(a) + float(b)}"}]
    # }
    # with open(log_file, "a", encoding="utf-8") as f:
    #     f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    return float(a) + float(b)


@mcp.tool()
def multiply(a: float, b: float) -> float:
    """Multiply two numbers (supports int and float)"""
    # log_file = get_config_value("LOG_FILE")
    # signature = get_config_value("SIGNATURE")
    # log_entry = {
    #     "signature": signature,
    #     "new_messages": [{"role": "tool:multiply", "content": f"{a} * {b} = {float(a) * float(b)}"}]
    # }
    # with open(log_file, "a", encoding="utf-8") as f:
    #     f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    return float(a) * float(b)


if __name__ == "__main__":
    port = int(os.getenv("MATH_HTTP_PORT", "8000"))
    mcp.run(transport="streamable-http", port=port)
