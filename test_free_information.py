#!/usr/bin/env python3
"""
Test information gathering with FREE alternatives (no API keys required)
This demonstrates the agentic capability without needing Jina AI
"""

import asyncio
import requests
from bs4 import BeautifulSoup
from datetime import datetime


async def free_web_search(query: str, max_results: int = 3):
    """
    Free web search using DuckDuckGo HTML scraping
    No API key required!
    """
    try:
        # DuckDuckGo HTML search (no API needed)
        from duckduckgo_search import DDGS

        print(f"🔍 Searching for: {query}")
        results = DDGS().text(query, max_results=max_results)

        if not results:
            return []

        print(f"✅ Found {len(results)} results")
        return results

    except ImportError:
        print("⚠️  duckduckgo-search not installed. Install with:")
        print("   pip install duckduckgo-search")
        return []
    except Exception as e:
        print(f"❌ Search error: {e}")
        return []


async def scrape_content(url: str):
    """
    Simple web scraping using requests + BeautifulSoup
    No API key required!
    """
    try:
        print(f"📄 Scraping: {url}")

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()

        # Get title
        title = soup.find('title')
        title_text = title.get_text().strip() if title else "No title"

        # Get main content (try multiple strategies)
        content = ""

        # Strategy 1: Look for article tags
        article = soup.find('article')
        if article:
            paragraphs = article.find_all('p')
            content = ' '.join([p.get_text().strip() for p in paragraphs])

        # Strategy 2: Get all paragraphs
        if not content:
            paragraphs = soup.find_all('p')
            content = ' '.join([p.get_text().strip() for p in paragraphs[:15]])

        # Strategy 3: Get body text
        if not content:
            body = soup.find('body')
            content = body.get_text() if body else soup.get_text()

        # Clean up whitespace
        content = ' '.join(content.split())

        return {
            'url': url,
            'title': title_text,
            'content': content[:2000],  # Limit to first 2000 chars
            'scraped_at': datetime.now().isoformat()
        }

    except Exception as e:
        return {
            'url': url,
            'error': str(e)
        }


async def test_information_gathering():
    """Test information gathering without API keys"""

    print("=" * 70)
    print("FREE Information Gathering Test (No API Keys Required!)")
    print("=" * 70)
    print()

    # Test queries related to stocks
    test_queries = [
        "NVIDIA stock latest news",
        "Tesla earnings report 2025"
    ]

    for i, query in enumerate(test_queries, 1):
        print(f"\n{'=' * 70}")
        print(f"Test {i}/{len(test_queries)}")
        print("=" * 70)

        # Search
        search_results = await free_web_search(query, max_results=2)

        if not search_results:
            print(f"⚠️  No results for: {query}")
            continue

        # Process first result
        first_result = search_results[0]
        print(f"\n📌 Title: {first_result.get('title', 'N/A')}")
        print(f"🔗 URL: {first_result.get('href', 'N/A')}")

        # Scrape content
        scraped = await scrape_content(first_result['href'])

        if 'error' in scraped:
            print(f"❌ Scraping failed: {scraped['error']}")
        else:
            print(f"\n✅ Successfully scraped content!")
            print(f"📝 Content preview (first 500 chars):")
            print("-" * 70)
            print(scraped['content'][:500])
            if len(scraped['content']) > 500:
                print(f"\n... ({len(scraped['content']) - 500} more characters)")
            print("-" * 70)

        print()

    print("\n" + "=" * 70)
    print("✅ FREE Information Gathering Test Complete!")
    print("=" * 70)
    print("\nThis demonstrates:")
    print("  ✅ Web search without API keys (DuckDuckGo)")
    print("  ✅ Web scraping without API keys (BeautifulSoup)")
    print("  ✅ Same capability as Jina AI, but FREE!")
    print("\nTo integrate with Claude Agent SDK:")
    print("  1. Replace Jina AI implementation in sdk_tools.py")
    print("  2. Use these free functions instead")
    print("  3. Agent works exactly the same way!")
    print()


if __name__ == "__main__":
    print("\n📦 Checking dependencies...")

    # Check if dependencies are installed
    try:
        import requests
        print("  ✅ requests installed")
    except ImportError:
        print("  ❌ requests not installed. Run: pip install requests")

    try:
        import bs4
        print("  ✅ beautifulsoup4 installed")
    except ImportError:
        print("  ❌ beautifulsoup4 not installed. Run: pip install beautifulsoup4")

    try:
        from duckduckgo_search import DDGS
        print("  ✅ duckduckgo-search installed")
    except ImportError:
        print("  ❌ duckduckgo-search not installed. Run: pip install duckduckgo-search")
        print("     (This is optional but recommended for search)")

    print()

    asyncio.run(test_information_gathering())
