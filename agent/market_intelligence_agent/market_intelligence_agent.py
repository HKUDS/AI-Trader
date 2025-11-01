"""
Market Intelligence Agent

This agent periodically reviews market news and updates the intelligence database
with curated, concise narratives about:
- Fed policy and monetary conditions
- Global economic trends
- Sector performance and rotation
- Major market events
- Geopolitical developments

It keeps information current and relevant while avoiding information overload.
"""

import os
import sys
from datetime import datetime
from typing import Dict, Optional, List

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from dotenv import load_dotenv
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, tool, create_sdk_mcp_server

from tools.market_intelligence import MarketIntelligence
from tools.general_tools import get_config_value

load_dotenv()


# ============================================================================
# INTELLIGENCE TOOLS
# ============================================================================

@tool(
    name="update_fed_policy",
    description="""Update Federal Reserve and monetary policy intelligence.
    Use this to record Fed decisions, rate changes, policy statements, and commentary.
    Keep it concise - 1 sentence summary, 2-3 sentence details.""",
    input_schema={
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "1-sentence summary of the Fed policy update"
            },
            "details": {
                "type": "string",
                "description": "2-3 sentences with key details"
            },
            "importance": {
                "type": "integer",
                "description": "Importance 1-10 (10=critical)",
                "default": 5
            }
        },
        "required": ["summary", "details"]
    }
)
async def update_fed_policy(args: Dict) -> Dict:
    """Update Fed policy intelligence"""
    intel = MarketIntelligence()
    date = get_config_value("TODAY_DATE") or datetime.now().strftime("%Y-%m-%d")

    success = intel.update_intelligence(
        date=date,
        category="fed_policy",
        summary=args["summary"],
        details=args["details"],
        importance=args.get("importance", 5)
    )

    return {
        "content": [{
            "type": "text",
            "text": f"✅ Fed policy intelligence updated for {date}"
        }]
    }


@tool(
    name="update_global_economy",
    description="""Update global economic conditions intelligence.
    Record GDP, inflation, employment, consumer sentiment, and international economic trends.
    Keep it concise and focused on tradeable insights.""",
    input_schema={
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "1-sentence summary of economic conditions"
            },
            "details": {
                "type": "string",
                "description": "2-3 sentences with key economic data and trends"
            },
            "importance": {
                "type": "integer",
                "description": "Importance 1-10",
                "default": 5
            }
        },
        "required": ["summary", "details"]
    }
)
async def update_global_economy(args: Dict) -> Dict:
    """Update global economy intelligence"""
    intel = MarketIntelligence()
    date = get_config_value("TODAY_DATE") or datetime.now().strftime("%Y-%m-%d")

    intel.update_intelligence(
        date=date,
        category="global_economy",
        summary=args["summary"],
        details=args["details"],
        importance=args.get("importance", 5)
    )

    return {
        "content": [{
            "type": "text",
            "text": f"✅ Global economy intelligence updated for {date}"
        }]
    }


@tool(
    name="update_sector_trends",
    description="""Update sector performance and rotation trends.
    Track which sectors are leading/lagging, rotation patterns, and industry-specific developments.
    Focus on actionable sector insights for tech/NASDAQ 100 stocks.""",
    input_schema={
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "1-sentence summary of sector trends"
            },
            "details": {
                "type": "string",
                "description": "2-3 sentences on sector performance and rotation"
            },
            "importance": {
                "type": "integer",
                "description": "Importance 1-10",
                "default": 5
            }
        },
        "required": ["summary", "details"]
    }
)
async def update_sector_trends(args: Dict) -> Dict:
    """Update sector trends intelligence"""
    intel = MarketIntelligence()
    date = get_config_value("TODAY_DATE") or datetime.now().strftime("%Y-%m-%d")

    intel.update_intelligence(
        date=date,
        category="sector_trends",
        summary=args["summary"],
        details=args["details"],
        importance=args.get("importance", 5)
    )

    return {
        "content": [{
            "type": "text",
            "text": f"✅ Sector trends intelligence updated for {date}"
        }]
    }


@tool(
    name="update_major_events",
    description="""Update major market events intelligence.
    Record earnings seasons, product launches, regulatory changes, corporate actions.
    Focus on events affecting NASDAQ 100 and tech sector.""",
    input_schema={
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "1-sentence summary of the major event"
            },
            "details": {
                "type": "string",
                "description": "2-3 sentences with event details and market impact"
            },
            "importance": {
                "type": "integer",
                "description": "Importance 1-10",
                "default": 5
            }
        },
        "required": ["summary", "details"]
    }
)
async def update_major_events(args: Dict) -> Dict:
    """Update major events intelligence"""
    intel = MarketIntelligence()
    date = get_config_value("TODAY_DATE") or datetime.now().strftime("%Y-%m-%d")

    intel.update_intelligence(
        date=date,
        category="major_events",
        summary=args["summary"],
        details=args["details"],
        importance=args.get("importance", 5)
    )

    return {
        "content": [{
            "type": "text",
            "text": f"✅ Major events intelligence updated for {date}"
        }]
    }


@tool(
    name="update_geopolitical",
    description="""Update geopolitical intelligence.
    Track trade policy, international conflicts, regulatory changes affecting markets.
    Focus on tradeable implications for tech and global supply chains.""",
    input_schema={
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "1-sentence summary of geopolitical development"
            },
            "details": {
                "type": "string",
                "description": "2-3 sentences on implications for markets"
            },
            "importance": {
                "type": "integer",
                "description": "Importance 1-10",
                "default": 5
            }
        },
        "required": ["summary", "details"]
    }
)
async def update_geopolitical(args: Dict) -> Dict:
    """Update geopolitical intelligence"""
    intel = MarketIntelligence()
    date = get_config_value("TODAY_DATE") or datetime.now().strftime("%Y-%m-%d")

    intel.update_intelligence(
        date=date,
        category="geopolitical",
        summary=args["summary"],
        details=args["details"],
        importance=args.get("importance", 5)
    )

    return {
        "content": [{
            "type": "text",
            "text": f"✅ Geopolitical intelligence updated for {date}"
        }]
    }


@tool(
    name="search_news",
    description="""Search for market news and information.
    Use this to gather information before updating intelligence categories.
    Returns recent news articles and analysis.""",
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query for market news"
            }
        },
        "required": ["query"]
    }
)
async def search_news(args: Dict) -> Dict:
    """Search for news - uses Jina search"""
    import requests
    import random
    from datetime import timedelta

    query = args["query"]
    api_key = os.environ.get("JINA_API_KEY")

    if not api_key:
        return {
            "content": [{
                "type": "text",
                "text": "Error: JINA_API_KEY not set"
            }]
        }

    try:
        # Search
        url = f'https://s.jina.ai/?q={query}&n=3'
        headers = {
            'Authorization': f'Bearer {api_key}',
            "Accept": "application/json",
            "X-Respond-With": "no-content"
        }

        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

        if not data or 'data' not in data:
            return {"content": [{"type": "text", "text": "No results found"}]}

        # Get URLs
        urls = [item['url'] for item in data.get('data', [])[:2] if 'url' in item]

        if not urls:
            return {"content": [{"type": "text", "text": "No results found"}]}

        # Scrape first URL
        url = urls[0]
        jina_url = f'https://r.jina.ai/{url}'
        headers = {
            "Accept": "application/json",
            'Authorization': api_key,
            'X-Timeout': "10",
        }

        response = requests.get(jina_url, headers=headers)
        if response.status_code != 200:
            return {"content": [{"type": "text", "text": f"Error fetching {url}"}]}

        article_data = response.json()['data']

        result = f"""
URL: {article_data['url']}
Title: {article_data['title']}
Published: {article_data.get('publishedTime', 'unknown')}
Content: {article_data['content'][:1500]}...
"""

        return {"content": [{"type": "text", "text": result}]}

    except Exception as e:
        return {"content": [{"type": "text", "text": f"Search error: {str(e)}"}]}


def create_intelligence_server():
    """Create MCP server with intelligence tools"""
    return create_sdk_mcp_server(
        name="market-intelligence-tools",
        tools=[
            update_fed_policy,
            update_global_economy,
            update_sector_trends,
            update_major_events,
            update_geopolitical,
            search_news
        ]
    )


# ============================================================================
# MARKET INTELLIGENCE AGENT
# ============================================================================

INTELLIGENCE_SYSTEM_PROMPT = """You are a Market Intelligence Curator for a trading system.

Your role is to maintain a concise, current narrative of market conditions across 5 categories:
1. Federal Reserve & Monetary Policy
2. Global Economic Conditions
3. Sector Trends & Rotation
4. Major Market Events
5. Geopolitical Factors

=== YOUR TASK ===

Review recent market news and update the intelligence database. Focus on:
- **Conciseness**: 1 sentence summary, 2-3 sentence details max
- **Relevance**: Information that affects NASDAQ 100 / tech stock trading decisions
- **Currency**: Update when significant changes occur
- **Actionability**: Focus on tradeable insights, not noise

=== GUIDELINES ===

**Fed Policy**: Interest rate decisions, policy statements, inflation outlook
**Global Economy**: GDP, inflation, employment, consumer data, international trends
**Sector Trends**: Which sectors are hot/cold, rotation patterns, industry developments
**Major Events**: Earnings seasons, product launches, regulatory changes, M&A
**Geopolitical**: Trade policy, conflicts, regulations affecting markets

=== WORKFLOW ===

1. Search for news in each category (use search_news tool)
2. Synthesize findings into concise narratives
3. Update intelligence for categories with significant new information
4. Prioritize high-importance developments (rate: 7-10)
5. When done, output <INTELLIGENCE_UPDATE_COMPLETE>

=== IMPORTANCE SCALE ===

10: Market-moving (Fed rate change, major crisis)
8-9: Highly significant (Strong GDP, sector rotation)
6-7: Important (Earnings trends, policy shifts)
4-5: Notable (Individual stock news, minor data)
1-3: Background (Long-term trends, context)

Focus on information rated 6+ for today's update.

Today's date: {date}

Begin your market intelligence review.
"""


class MarketIntelligenceAgent:
    """
    Agent that curates market intelligence narratives.
    """

    def __init__(
        self,
        anthropic_api_key: Optional[str] = None,
        basemodel: str = "sonnet"
    ):
        self.anthropic_api_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
        self.basemodel = basemodel

        if not self.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY must be set")

        self.client: Optional[ClaudeSDKClient] = None
        self.intelligence_server = None

    async def initialize(self):
        """Initialize the agent"""
        print("🔍 Initializing Market Intelligence Agent")

        self.intelligence_server = create_intelligence_server()

        options = ClaudeAgentOptions(
            model=self.basemodel,
            mcp_servers=[self.intelligence_server],
            max_turns=20
        )

        self.client = ClaudeSDKClient(options)
        print("✅ Market Intelligence Agent initialized")

    async def update_intelligence(self, date: str):
        """
        Run intelligence update for a specific date.

        Args:
            date: Date to update intelligence for (YYYY-MM-DD)
        """
        print(f"📰 Updating market intelligence for {date}")

        # Set system prompt with date
        prompt = INTELLIGENCE_SYSTEM_PROMPT.format(date=date)
        self.client.options.system_prompt = prompt

        # Send query
        query = (
            f"Review today's market news and update the intelligence database. "
            f"Focus on the 5 key categories and prioritize importance 6+. "
            f"Be concise and actionable."
        )

        await self.client.query(query)

        # Process responses
        step = 0
        max_steps = 20

        while step < max_steps:
            step += 1
            response = await self.client.receive_response()

            content = response.get("content", "")
            if isinstance(content, str):
                print(f"   Step {step}: {content[:100]}...")

                if "<INTELLIGENCE_UPDATE_COMPLETE>" in content:
                    print("✅ Intelligence update complete")
                    break

            if response.get("is_done", False):
                print("✅ Agent completed")
                break

        print(f"📊 Market intelligence updated for {date}")


if __name__ == "__main__":
    import anyio
    from tools.general_tools import write_config_value

    async def test():
        # Set date
        write_config_value("TODAY_DATE", "2025-10-15")

        # Create and run agent
        agent = MarketIntelligenceAgent()
        await agent.initialize()
        await agent.update_intelligence("2025-10-15")

        # Show results
        intel = MarketIntelligence()
        context = intel.build_intelligence_context("2025-10-15")
        print("\n" + "="*60)
        print(context)

    anyio.run(test)
