"""
Claude Agent SDK Tools - SECURE VERSION with AI Poisoning Prevention

This version includes content sanitization to prevent:
- Prompt injection attacks
- AI poisoning from malicious web content
- Trading manipulation through fake information
"""

import os
import json
import sys
from typing import Dict, Any
from pathlib import Path

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from claude_agent_sdk import tool, create_sdk_mcp_server
from tools.price_tools import get_latest_position, get_open_prices
from tools.general_tools import get_config_value, write_config_value

# Import security components
from agent_tools.content_sanitizer import ContentSanitizer

# Import search functionality
import requests
import random
import re
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# Initialize content sanitizer (SECURITY)
content_sanitizer = ContentSanitizer(
    max_content_length=5000,  # Limit to 5KB
    strict_mode=True,  # Aggressive filtering
    block_on_detection=True  # Block high-risk content
)

# (Note: buy, sell, and get_price_local tools remain the same - only showing updated get_information)

@tool(
    name="get_information",
    description="""Use search tool to scrape and return main content information related to specified query.
Returns web page contents including URL, title, description, publish time, and content.

⚠️ SECURITY: All content is sanitized to prevent prompt injection and AI poisoning.""",
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Key information or search terms you want to retrieve"
            }
        },
        "required": ["query"]
    }
)
async def get_information_secure(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Search and retrieve information using claude-agent-sdk tool format

    INCLUDES SECURITY: Content sanitization to prevent AI poisoning
    """
    query = args["query"]

    # Helper functions for Jina search (same as before)
    def parse_date_to_standard(date_str: str) -> str:
        if not date_str or date_str == 'unknown':
            return 'unknown'

        # Handle relative time
        if 'ago' in date_str.lower():
            try:
                now = datetime.now()
                if 'hour' in date_str.lower():
                    hours = int(re.findall(r'\d+', date_str)[0])
                    return (now - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
                elif 'day' in date_str.lower():
                    days = int(re.findall(r'\d+', date_str)[0])
                    return (now - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                pass

        # Handle ISO 8601
        try:
            if 'T' in date_str:
                date_part = date_str.split('+')[0] if '+' in date_str else date_str.replace('Z', '')
                if '.' in date_part:
                    parsed = datetime.strptime(date_part.split('.')[0], '%Y-%m-%dT%H:%M:%S')
                else:
                    parsed = datetime.strptime(date_part, '%Y-%m-%dT%H:%M:%S')
                return parsed.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            pass

        return date_str

    def jina_search(query: str, api_key: str):
        url = f'https://s.jina.ai/?q={query}&n=1'
        headers = {
            'Authorization': f'Bearer {api_key}',
            "Accept": "application/json",
            "X-Respond-With": "no-content"
        }

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            json_data = response.json()

            if not json_data or 'data' not in json_data:
                return []

            filtered_urls = []
            for item in json_data.get('data', []):
                if 'url' not in item:
                    continue

                raw_date = item.get('date', 'unknown')
                standardized_date = parse_date_to_standard(raw_date)

                if standardized_date == 'unknown':
                    filtered_urls.append(item['url'])
                    continue

                today_date = get_config_value("TODAY_DATE")
                if today_date and today_date > standardized_date:
                    filtered_urls.append(item['url'])
                else:
                    filtered_urls.append(item['url'])

            return filtered_urls
        except Exception as e:
            logger.error(f"Jina search error: {e}")
            return []

    def jina_scrape(url: str, api_key: str):
        try:
            jina_url = f'https://r.jina.ai/{url}'
            headers = {
                "Accept": "application/json",
                'Authorization': api_key,
                'X-Timeout': "10",
                "X-With-Generated-Alt": "true",
            }
            response = requests.get(jina_url, headers=headers)

            if response.status_code != 200:
                return {'url': url, 'error': f"Status {response.status_code}"}

            data = response.json()['data']
            return {
                'url': data['url'],
                'title': data['title'],
                'description': data['description'],
                'content': data['content'],
                'publish_time': data.get('publishedTime', 'unknown')
            }
        except Exception as e:
            return {'url': url, 'error': str(e)}

    # Main search logic
    try:
        api_key = os.environ.get("JINA_API_KEY")
        if not api_key:
            return {
                "content": [{
                    "type": "text",
                    "text": "Error: Jina API key not provided! Please set JINA_API_KEY environment variable."
                }]
            }

        urls = jina_search(query, api_key)
        if not urls:
            return {
                "content": [{
                    "type": "text",
                    "text": f"⚠️ Search query '{query}' found no results."
                }]
            }

        if len(urls) > 1:
            urls = random.sample(urls, 1)

        results = []
        for url in urls:
            result = jina_scrape(url, api_key)
            if 'error' in result:
                results.append(f"Error: {result['error']}")
            else:
                # ===== SECURITY: SANITIZE CONTENT BEFORE RETURNING =====
                raw_content = result['content']

                # Sanitize the content
                sanitization_result = content_sanitizer.sanitize(
                    content=raw_content,
                    source_url=url
                )

                # Log security events
                if not sanitization_result.is_safe:
                    logger.warning(
                        f"🚨 SECURITY: Blocked malicious content from {url}\n"
                        f"   Risk Score: {sanitization_result.risk_score:.2f}\n"
                        f"   Threats: {sanitization_result.threats_detected}"
                    )
                    results.append(f"""
⚠️ SECURITY WARNING ⚠️
Content from {url} was blocked due to security concerns.
Risk Score: {sanitization_result.risk_score:.2f}
Detected Threats: {len(sanitization_result.threats_detected)}

This content may contain:
- Prompt injection attempts
- Malicious instructions
- AI poisoning attempts

Recommendation: Find alternative sources for this query.
""")
                    continue

                elif sanitization_result.threats_detected:
                    logger.info(
                        f"🛡️  SECURITY: Sanitized content from {url}\n"
                        f"   Removed {len(sanitization_result.threats_detected)} threats\n"
                        f"   Threats: {sanitization_result.threats_detected[:3]}"
                    )

                # Use sanitized content
                safe_content = sanitization_result.sanitized_content

                results.append(f"""
URL: {result['url']}
Title: {result['title']}
Description: {result['description']}
Publish Time: {result['publish_time']}
Content: {safe_content[:1000]}...

[Content has been sanitized for security]
""")

        return {
            "content": [{
                "type": "text",
                "text": "\n".join(results) if results else f"⚠️ No safe results for '{query}'"
            }]
        }

    except Exception as e:
        logger.error(f"Search tool execution failed: {str(e)}")
        return {
            "content": [{
                "type": "text",
                "text": f"❌ Search tool execution failed: {str(e)}"
            }]
        }


# Example of how to create server with secure tools
def create_secure_trading_server():
    """
    Create MCP server with security-enhanced tools

    All web content is sanitized before being passed to the agent
    """
    # Import the original tools (buy, sell, get_price_local)
    from agent.claude_sdk_agent.sdk_tools import buy, sell, get_price_local

    return create_sdk_mcp_server(
        name="secure-trading-tools",
        tools=[buy, sell, get_price_local, get_information_secure]
    )


if __name__ == "__main__":
    print("=" * 70)
    print("SECURE SDK TOOLS - with AI Poisoning Prevention")
    print("=" * 70)
    print("\n✅ Module loaded successfully")
    print("\nTools available:")
    print("  🔧 buy() - Buy stocks")
    print("  🔧 sell() - Sell stocks")
    print("  🔧 get_price_local() - Get historical prices")
    print("  🔧 get_information_secure() - Search with sanitization 🛡️")
    print("\n🛡️  Security Features:")
    print("  ✅ Prompt injection detection")
    print("  ✅ AI poisoning prevention")
    print("  ✅ Content sanitization")
    print("  ✅ Risk scoring and blocking")
    print("\n" + "=" * 70)
