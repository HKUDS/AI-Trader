"""
Claude Agent SDK Tools with Domain List Security

CRITICAL SECURITY ARCHITECTURE:
1. Check blacklist → Block BEFORE fetching (protects bandwidth + LLM)
2. Check whitelist → Use fast regex only (trusted sources)
3. Unknown domains → Fetch → Full scan → Auto-blacklist if malicious
4. Content NEVER reaches LLM until approved by security layer

This ensures the LLM only sees pre-vetted, sanitized content.
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

# Import security components
try:
    from agent_tools.domain_lists import get_domain_manager
    from agent_tools.security_logger import get_security_logger
    from agent_tools.production_security import get_security_instance
    from agent_tools.content_sanitizer import ContentSanitizer
    SECURITY_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  Security modules not available: {e}")
    SECURITY_AVAILABLE = False

# Import search functionality
import requests
import random
import re
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# Initialize security components (if available)
if SECURITY_AVAILABLE:
    domain_manager = get_domain_manager()
    security_logger = get_security_logger()
    # Fast regex scanner for whitelisted domains
    whitelist_scanner = ContentSanitizer(strict_mode=False, block_on_detection=False)
    # Full security scanner for unknown domains
    full_scanner = get_security_instance(fast_mode=True)
else:
    domain_manager = None
    security_logger = None
    whitelist_scanner = None
    full_scanner = None


# Import existing buy, sell, get_price_local from original tools
from agent.claude_sdk_agent.sdk_tools import (
    buy,
    sell,
    get_price_local
)


@tool(
    name="get_information",
    description="""Search and retrieve information with comprehensive security.

SECURITY FEATURES:
- Blacklist check (blocks malicious domains before fetching)
- Whitelist check (trusted domains use fast scanning)
- Full security scan for unknown domains
- Auto-blacklisting of malicious content
- Human review queue for flagged domains

Content is thoroughly vetted BEFORE reaching the agent.""",
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query or keywords"
            }
        },
        "required": ["query"]
    }
)
async def get_information_secure(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Secure information gathering with domain lists

    SECURITY FLOW:
    1. Search for URLs
    2. CHECK BLACKLIST → Block if malicious
    3. CHECK WHITELIST → Fast scan if trusted
    4. Unknown domain → Fetch → Full scan → Auto-blacklist if needed
    5. Return only sanitized content to LLM
    """
    query = args["query"]

    if not SECURITY_AVAILABLE:
        return {
            "content": [{
                "type": "text",
                "text": "⚠️ Security system not available. Install required modules."
            }]
        }

    # Helper functions (same as original)
    def parse_date_to_standard(date_str: str) -> str:
        if not date_str or date_str == 'unknown':
            return 'unknown'

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
        url = f'https://s.jina.ai/?q={query}&n=3'  # Get top 3 results
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

    # ========================================================================
    # MAIN SECURITY LOGIC
    # ========================================================================

    try:
        api_key = os.environ.get("JINA_API_KEY")
        if not api_key:
            return {
                "content": [{
                    "type": "text",
                    "text": "Error: JINA_API_KEY not set. Set environment variable."
                }]
            }

        # Step 1: Search for URLs
        urls = jina_search(query, api_key)
        if not urls:
            return {
                "content": [{
                    "type": "text",
                    "text": f"⚠️ No search results for '{query}'"
                }]
            }

        logger.info(f"🔍 Found {len(urls)} URLs for query: {query}")

        # Step 2: Filter and process URLs with security checks
        results = []

        for url in urls[:3]:  # Process top 3
            # ============================================================
            # SECURITY CHECKPOINT 1: BLACKLIST CHECK
            # Block BEFORE fetching (saves bandwidth and protects LLM)
            # ============================================================
            if domain_manager.is_blacklisted(url):
                reason = domain_manager.get_blacklist_reason(url)
                security_logger.log_blocked_domain(url, reason)

                results.append(
                    f"🚫 BLOCKED: {url}\n"
                    f"Reason: {reason}\n"
                    f"This domain has been blacklisted due to previous malicious activity.\n"
                )
                continue  # Skip to next URL

            # ============================================================
            # SECURITY CHECKPOINT 2: WHITELIST CHECK
            # Trusted domains get fast regex-only scanning
            # ============================================================
            is_whitelisted = domain_manager.is_whitelisted(url)

            if is_whitelisted:
                security_logger.log_whitelisted_bypass(url)
                logger.info(f"✅ Whitelisted domain: {url} (fast scan only)")

            # Fetch content (blacklisted domains already filtered out)
            scraped = jina_scrape(url, api_key)

            if 'error' in scraped:
                results.append(f"Error fetching {url}: {scraped['error']}")
                continue

            raw_content = scraped['content']

            # ============================================================
            # SECURITY CHECKPOINT 3: CONTENT SCANNING
            # Whitelist → Fast regex
            # Unknown → Full llm-guard scan
            # ============================================================

            if is_whitelisted:
                # Fast regex scan for trusted sources
                scan_result = whitelist_scanner.sanitize(raw_content, url)
                security_mode = "whitelist_regex"
            else:
                # Full security scan for unknown domains
                scan_result = full_scanner.scan(raw_content, url)
                security_mode = f"{scan_result.get('mode', 'unknown')}_full"

                # Log the scan
                security_logger.log_full_scan(
                    url,
                    scan_result.get('risk_score', 0.0),
                    scan_result.get('is_safe', False)
                )

            # ============================================================
            # SECURITY CHECKPOINT 4: AUTO-BLACKLIST
            # If malicious content detected → blacklist domain
            # ============================================================

            if not scan_result.get('is_safe', False):
                threats = scan_result.get('threats', [])
                risk_score = scan_result.get('risk_score', 1.0)

                # Log malicious content
                security_logger.log_malicious_content(
                    url,
                    threats,
                    risk_score,
                    raw_content[:200]
                )

                # AUTO-BLACKLIST the domain
                domain_manager.add_to_blacklist(
                    url=url,
                    reason=f"Malicious content detected: {', '.join(threats[:3])}",
                    threats=threats,
                    risk_score=risk_score,
                    auto_added=True
                )

                # Log auto-blacklist
                security_logger.log_auto_blacklist(
                    url,
                    "Malicious content detected",
                    threats
                )

                # Return warning to LLM
                results.append(
                    f"🚨 BLOCKED & BLACKLISTED: {url}\n"
                    f"Risk Score: {risk_score:.2f}\n"
                    f"Threats: {', '.join(threats[:5])}\n"
                    f"This domain has been automatically blacklisted and flagged for human review.\n"
                )
                continue

            # ============================================================
            # CHECKPOINT PASSED: Return sanitized content to LLM
            # ============================================================

            safe_content = scan_result.get('sanitized_content', raw_content)

            results.append(f"""
URL: {scraped['url']}
Title: {scraped['title']}
Description: {scraped['description']}
Published: {scraped['publish_time']}
Security: {security_mode}

Content:
{safe_content[:1500]}...

[Content scanned and sanitized]
""")

        # Return results
        if not results:
            return {
                "content": [{
                    "type": "text",
                    "text": f"⚠️ All results for '{query}' were blocked by security filters."
                }]
            }

        return {
            "content": [{
                "type": "text",
                "text": "\n---\n".join(results)
            }]
        }

    except Exception as e:
        logger.error(f"Error in get_information: {e}")
        return {
            "content": [{
                "type": "text",
                "text": f"❌ Search failed: {str(e)}"
            }]
        }


# Create MCP server with secure tools
def create_secure_trading_server():
    """
    Create MCP server with comprehensive security

    Features:
    - Domain blacklist/whitelist
    - Pre-LLM security scanning
    - Auto-blacklisting
    - Security logging
    """
    return create_sdk_mcp_server(
        name="secure-trading-tools-with-lists",
        tools=[buy, sell, get_price_local, get_information_secure]
    )


if __name__ == "__main__":
    print("=" * 70)
    print("SECURE TRADING TOOLS - With Domain Lists")
    print("=" * 70)
    print("\n✅ Module loaded successfully")
    print("\nSecurity Features:")
    print("  🚫 Blacklist protection (blocks before fetching)")
    print("  ✅ Whitelist fast-track (regex only for trusted sources)")
    print("  🔍 Full scanning for unknown domains")
    print("  🚨 Auto-blacklisting of malicious sources")
    print("  📋 Human review queue")
    print("  📊 Security event logging")
    print("\n" + "=" * 70)

    if SECURITY_AVAILABLE:
        print("\n📊 Current Security Status:")
        stats = domain_manager.get_stats()
        for key, value in stats.items():
            print(f"   {key}: {value}")
    else:
        print("\n⚠️  Security modules not available")

    print("\n" + "=" * 70)
