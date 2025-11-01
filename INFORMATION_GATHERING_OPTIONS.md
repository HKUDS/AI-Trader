# Information Gathering Options for Claude Agent SDK

## Current Implementation: Jina AI ✅

**Status:** Currently using Jina AI for web search and content scraping

**Why Jina AI?**
- Simple API for search + scraping
- Single service for both operations
- Good content extraction quality
- Reasonable pricing

## Alternative Options

### 1. Built-in Claude Web Search (If Available)

```python
# Check if your Claude API tier includes web search
# Some Claude API plans include built-in search capabilities
```

**Pros:**
- No external API needed
- Direct integration with Claude
- No additional cost

**Cons:**
- May not be available in all API tiers
- Need to check Anthropic's current offerings

### 2. Brave Search API

```python
import requests

@tool(name="brave_search", ...)
async def brave_search(args):
    api_key = os.getenv("BRAVE_API_KEY")
    url = f"https://api.search.brave.com/res/v1/web/search"
    params = {"q": args["query"]}
    headers = {"X-Subscription-Token": api_key}

    response = requests.get(url, params=params, headers=headers)
    return parse_results(response.json())
```

**Pros:**
- Privacy-focused
- Good search quality
- Free tier available

**Cons:**
- Separate scraping needed
- Rate limits on free tier

### 3. Google Custom Search API

```python
@tool(name="google_search", ...)
async def google_search(args):
    api_key = os.getenv("GOOGLE_API_KEY")
    search_engine_id = os.getenv("GOOGLE_CSE_ID")
    # Implementation...
```

**Pros:**
- High-quality results
- Well-documented
- Reliable service

**Cons:**
- Limited free quota (100 searches/day)
- Requires separate scraping
- Setup complexity

### 4. SerpAPI (Google/Bing/etc. aggregator)

```python
@tool(name="serp_search", ...)
async def serp_search(args):
    api_key = os.getenv("SERPAPI_KEY")
    # Access multiple search engines
```

**Pros:**
- Multiple search engines
- Structured data
- Easy to use

**Cons:**
- Paid service
- Still need separate scraping

### 5. Custom Web Scraping (No Search API)

```python
from playwright.async_api import async_playwright
import requests
from bs4 import BeautifulSoup

@tool(name="scrape_url", ...)
async def scrape_url(args):
    """Direct scraping if you already know the URL"""
    url = args["url"]

    # Simple scraping
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')

    # Or JavaScript-heavy sites
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(url)
        content = await page.content()
        # Parse content...
```

**Pros:**
- No API costs
- Full control
- No rate limits

**Cons:**
- No search capability (need URLs)
- More maintenance
- Potential blocking issues

### 6. Hybrid Approach: DuckDuckGo + Scraping

```python
from duckduckgo_search import DDGS

@tool(name="ddg_search", ...)
async def ddg_search(args):
    """Free search without API key"""
    query = args["query"]

    # Free DuckDuckGo search
    results = DDGS().text(query, max_results=5)

    # Then scrape the URLs
    for result in results:
        url = result["href"]
        content = scrape_content(url)
        # Process...
```

**Pros:**
- Completely free
- No API keys needed
- Good privacy

**Cons:**
- Unofficial library
- May break with website changes
- Rate limiting can be aggressive

## Recommendation Matrix

| Use Case | Best Option | Why |
|----------|-------------|-----|
| **Current setup works** | Keep Jina AI | Simple, works well |
| **Want free solution** | DuckDuckGo + Scraping | No API costs |
| **Need reliability** | Google Custom Search | Well-supported |
| **Privacy focused** | Brave Search | Privacy-first design |
| **High volume** | SerpAPI | Multiple sources |
| **Known URLs only** | Direct scraping | No search needed |

## How to Switch (Example: Brave Search)

### Step 1: Get API Key
```bash
# Sign up at https://brave.com/search/api/
export BRAVE_API_KEY="your_key"
```

### Step 2: Update Tool Implementation
```python
# In agent/claude_sdk_agent/sdk_tools.py

@tool(
    name="get_information",
    description="Search using Brave and scrape content",
    input_schema={...}
)
async def get_information(args):
    query = args["query"]

    # Search with Brave
    brave_results = await brave_search(query)

    # Scrape top result
    url = brave_results[0]["url"]
    content = await scrape_url(url)

    return {"content": [{"type": "text", "text": content}]}
```

### Step 3: Update .env
```bash
# .env
BRAVE_API_KEY=your_brave_api_key
# Remove JINA_API_KEY if not using
```

## Current Implementation Details

The system currently uses Jina AI because:

1. **Single API** - Search + Scraping in one service
2. **Clean extraction** - Good at removing ads, extracting main content
3. **Markdown output** - Returns clean, structured text
4. **Date filtering** - Can filter results by publication date
5. **Simple integration** - Easy to implement

```python
# Current flow in sdk_tools.py:
1. jina_search(query) → Get URLs
2. jina_scrape(url) → Extract content
3. Return structured data
```

## No API Key? Use This Free Alternative

```python
# Install: pip install duckduckgo-search beautifulsoup4

from duckduckgo_search import DDGS
import requests
from bs4 import BeautifulSoup

@tool(name="get_information_free", ...)
async def get_information_free(args):
    """Free web search and scraping"""
    query = args["query"]

    # Free search
    results = DDGS().text(query, max_results=3)

    if not results:
        return {"content": [{"type": "text", "text": "No results found"}]}

    # Scrape first result
    url = results[0]["href"]
    title = results[0]["title"]

    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract main content (basic version)
        paragraphs = soup.find_all('p')
        content = ' '.join([p.get_text() for p in paragraphs[:10]])

        return {
            "content": [{
                "type": "text",
                "text": f"Title: {title}\nURL: {url}\n\nContent: {content[:1000]}..."
            }]
        }
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Error: {str(e)}"}]}
```

## Summary

**Answer to your question:**
- ❌ Claude Agent SDK **does not** include web search built-in
- ✅ You **need** an external service for web information
- ✅ Jina AI is **one option** (currently used)
- ✅ Many **free alternatives** exist (DuckDuckGo, etc.)
- ✅ Can **easily switch** by modifying the tool implementation

**The Claude Agent SDK provides the framework, you choose the information source!**
