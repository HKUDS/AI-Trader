#!/usr/bin/env python3
"""
Test script for information gathering capability
Tests the get_information tool from the Claude SDK Agent
"""

import os
import asyncio
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import the tool
from agent.claude_sdk_agent.sdk_tools import get_information


async def test_information_gathering():
    """Test the get_information tool with a simple query"""

    print("=" * 60)
    print("Testing Information Gathering Capability")
    print("=" * 60)

    # Check if JINA_API_KEY is set
    jina_key = os.getenv("JINA_API_KEY")
    if not jina_key:
        print("❌ JINA_API_KEY not found in environment!")
        print("   Please set it in .env file or export it:")
        print("   export JINA_API_KEY='your_key_here'")
        return

    print(f"✅ JINA_API_KEY found: {jina_key[:10]}...")
    print()

    # Set a test date for context
    from tools.general_tools import write_config_value
    write_config_value("TODAY_DATE", "2025-10-20")

    # Test queries
    test_queries = [
        "Latest news about NVIDIA stock",
        "Tesla quarterly earnings 2025",
        "Apple stock market analysis"
    ]

    for i, query in enumerate(test_queries, 1):
        print(f"\n{'=' * 60}")
        print(f"Test {i}/{len(test_queries)}: {query}")
        print("=" * 60)

        try:
            # Call the tool
            result = await get_information({"query": query})

            # Extract the text content
            if "content" in result and len(result["content"]) > 0:
                text = result["content"][0].get("text", "No text returned")

                print("✅ Information retrieved successfully!")
                print("\nPreview (first 500 characters):")
                print("-" * 60)
                print(text[:500])
                if len(text) > 500:
                    print(f"\n... ({len(text) - 500} more characters)")
                print("-" * 60)
            else:
                print("⚠️ Unexpected result format:")
                print(json.dumps(result, indent=2))

        except Exception as e:
            print(f"❌ Error during test: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    print("Testing Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_information_gathering())
