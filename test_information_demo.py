#!/usr/bin/env python3
"""
Demo script showing how information gathering works
This demonstrates the tool structure without requiring API keys
"""

import asyncio
import json


def demo_information_tool():
    """Demonstrate how the get_information tool works"""

    print("=" * 60)
    print("Information Gathering Tool - DEMO")
    print("=" * 60)
    print()

    print("📋 Tool: get_information")
    print("-" * 60)
    print("Description:")
    print("  Uses Jina AI search to find and scrape web content")
    print("  Returns: URL, title, description, publish time, and content")
    print()

    print("Input Schema:")
    schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Key information or search terms you want to retrieve"
            }
        },
        "required": ["query"]
    }
    print(json.dumps(schema, indent=2))
    print()

    print("=" * 60)
    print("Example Usage Scenarios:")
    print("=" * 60)
    print()

    examples = [
        {
            "query": "Latest NVIDIA earnings report",
            "use_case": "Get recent financial news about a stock"
        },
        {
            "query": "Tesla production numbers Q3 2025",
            "use_case": "Find specific company metrics"
        },
        {
            "query": "Federal Reserve interest rate decision",
            "use_case": "Get macroeconomic information"
        },
        {
            "query": "Apple iPhone sales forecast",
            "use_case": "Research product performance"
        }
    ]

    for i, example in enumerate(examples, 1):
        print(f"\n{i}. {example['use_case']}")
        print(f"   Query: \"{example['query']}\"")
        print(f"   Would return: Web search results with scraped content")

    print("\n" + "=" * 60)
    print("Tool Workflow:")
    print("=" * 60)
    print("""
1. Agent decides it needs information
   └─> Calls: get_information({"query": "Latest NVIDIA news"})

2. Tool performs Jina AI search
   └─> Finds relevant URLs matching the query

3. Tool scrapes the content
   └─> Extracts title, description, publish time, content

4. Tool returns structured data
   └─> Agent receives information to make decisions

5. Agent uses information
   └─> Makes informed trading decisions based on news
    """)

    print("=" * 60)
    print("Integration with Claude Agent SDK:")
    print("=" * 60)
    print("""
The get_information tool is registered with the Claude SDK as:

@tool(
    name="get_information",
    description="Search and scrape web content...",
    input_schema={...}
)
async def get_information(args):
    query = args["query"]
    # Perform search and scraping
    return {"content": [{"type": "text", "text": results}]}

The agent can autonomously decide when to use this tool
based on its trading strategy and need for current information.
    """)

    print("=" * 60)
    print("Example Agent Interaction:")
    print("=" * 60)
    print("""
Agent Thought: "I should check recent news about NVIDIA before trading"
  ↓
Agent Action: get_information({"query": "NVIDIA stock news today"})
  ↓
Tool Result: [Article content about NVIDIA earnings, stock movement...]
  ↓
Agent Decision: "Based on positive earnings, I'll buy 10 shares"
  ↓
Agent Action: buy({"symbol": "NVDA", "amount": 10})
    """)

    print("\n" + "=" * 60)
    print("✅ This demonstrates the full agentic capability!")
    print("=" * 60)
    print("\nThe agent:")
    print("  ✅ Autonomously decides when to gather information")
    print("  ✅ Searches and analyzes web content")
    print("  ✅ Makes informed trading decisions")
    print("  ✅ True agentic behavior (not just tool calling)")
    print()


if __name__ == "__main__":
    demo_information_tool()
