import logging
import os
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv()
import json
import sys
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.general_tools import get_config_value

logger = logging.getLogger(__name__)


def parse_date_to_standard(date_str: str) -> str:
    """
    Convert various date formats to standard format (YYYY-MM-DD HH:MM:SS)

    Args:
        date_str: Date string in various formats, such as "20250410T0130", "2025-04-10 01:30:00"

    Returns:
        Standard format datetime string, such as "2025-04-10 01:30:00"
    """
    if not date_str or date_str == "unknown":
        return "unknown"

    # Handle Alpha Vantage format: "20250410T0130" (YYYYMMDDTHHMM) or "20251105T121200" (YYYYMMDDTHHMMSS)
    try:
        if "T" in date_str:
            date_part = date_str.split("T")[0]
            time_part = date_str.split("T")[1]
            if len(date_part) == 8:
                # Try format with seconds first: YYYYMMDDTHHMMSS (14 chars total)
                if len(time_part) == 6:
                    parsed_date = datetime.strptime(date_str, "%Y%m%dT%H%M%S")
                    return parsed_date.strftime("%Y-%m-%d %H:%M:%S")
                # Try format without seconds: YYYYMMDDTHHMM (12 chars total)
                elif len(time_part) == 4:
                    parsed_date = datetime.strptime(date_str, "%Y%m%dT%H%M")
                    return parsed_date.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass

    # Handle ISO 8601 format, such as "2025-04-10T01:30:00"
    try:
        if "T" in date_str:
            if "+" in date_str:
                date_part = date_str.split("+")[0]
            elif "Z" in date_str:
                date_part = date_str.replace("Z", "")
            else:
                date_part = date_str

            if "." in date_part:
                parsed_date = datetime.strptime(date_part.split(".")[0], "%Y-%m-%dT%H:%M:%S")
            else:
                parsed_date = datetime.strptime(date_part, "%Y-%m-%dT%H:%M:%S")
            return parsed_date.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass

    # Handle standard format "YYYY-MM-DD HH:MM:SS"
    try:
        if " " in date_str and len(date_str) >= 19:
            parsed_date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
            return parsed_date.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass

    # Handle date-only format "YYYY-MM-DD"
    try:
        if len(date_str) == 10 and date_str.count("-") == 2:
            parsed_date = datetime.strptime(date_str, "%Y-%m-%d")
            return parsed_date.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass

    # If unable to parse, return original string
    return date_str


class AlphaVantageNewsTool:
    def __init__(self):
        self.api_key = os.environ.get("ALPHAADVANTAGE_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Alpha Vantage API key not provided! Please set ALPHAADVANTAGE_API_KEY environment variable."
            )
        self.base_url = "https://www.alphavantage.co/query"

    def _fetch_news(
        self,
        tickers: Optional[str] = None,
        topics: Optional[str] = None,
        time_from: Optional[str] = None,
        time_to: Optional[str] = None,
        sort: str = "LATEST",
    ) -> List[Dict[str, Any]]:
        """
        Fetch news articles from Alpha Vantage NEWS_SENTIMENT API

        Args:
            tickers: Stock/crypto/forex symbols (e.g., "AAPL" or "COIN,CRYPTO:BTC,FOREX:USD")
            topics: News topics (e.g., "technology" or "technology,ipo")
            time_from: Start time in YYYYMMDDTHHMM format (e.g., "20220410T0130")
            time_to: End time in YYYYMMDDTHHMM format
            sort: Sort order ("LATEST", "EARLIEST", or "RELEVANCE")

        Returns:
            List of news articles
        """
        params = {
            "function": "NEWS_SENTIMENT",
            "apikey": self.api_key,
            "sort": sort,
            "limit": 20,  # Fixed limit
        }

        if tickers:
            params["tickers"] = tickers
        if topics:
            params["topics"] = topics
        if time_from:
            params["time_from"] = time_from
        if time_to:
            params["time_to"] = time_to

        try:
            response = requests.get(self.base_url, params=params, timeout=30)
            response.raise_for_status()

            json_data = response.json()
            
            # Check for API errors
            if "Error Message" in json_data:
                raise Exception(f"Alpha Vantage API error: {json_data['Error Message']}")
            if "Note" in json_data:
                raise Exception(f"Alpha Vantage API note: {json_data['Note']}")

            # Extract feed data
            feed = json_data.get("feed", [])
            
            if not feed:
                print(f"⚠️ Alpha Vantage API returned empty feed")
                return []

            return feed[:params["limit"]]

        except requests.exceptions.RequestException as e:
            logger.error(f"Alpha Vantage API request failed: {e}")
            raise Exception(f"Alpha Vantage API request failed: {e}")
        except Exception as e:
            logger.error(f"Alpha Vantage API error: {e}")
            raise

    def __call__(
        self,
        query: str,
        tickers: Optional[str] = None,
        topics: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for news articles with date filtering

        Args:
            query: Search query (currently used for logging, actual filtering is done by tickers/topics)
            tickers: Stock/crypto/forex symbols to filter by
            topics: News topics to filter by

        Returns:
            List of filtered news articles
        """
        print(f"Searching Alpha Vantage news: query={query}, tickers={tickers}, topics={topics}")

        # Get today's date for filtering
        today_date = get_config_value("TODAY_DATE")
        time_from = None
        time_to = None
        
        if today_date:
            # Convert TODAY_DATE to Alpha Vantage API format (YYYYMMDDTHHMM)
            # TODAY_DATE format is "YYYY-MM-DD HH:MM:SS" or "YYYY-MM-DD"
            try:
                if " " in today_date:
                    today_datetime = datetime.strptime(today_date, "%Y-%m-%d %H:%M:%S")
                else:
                    today_datetime = datetime.strptime(today_date, "%Y-%m-%d")
                # Convert to Alpha Vantage format: YYYYMMDDTHHMM
                time_to = today_datetime.strftime("%Y%m%dT%H%M")
                # Set time_from to 30 days before time_to (API may require both parameters)
                time_from_datetime = today_datetime - timedelta(days=30)
                time_from = time_from_datetime.strftime("%Y%m%dT%H%M")
                print(f"Filtering articles published before: {today_date} (API format: time_from={time_from}, time_to={time_to})")
            except Exception as e:
                logger.error(f"Failed to parse TODAY_DATE: {e}")
                print("⚠️ Failed to parse TODAY_DATE, returning all results without date filtering")
        else:
            print("⚠️ TODAY_DATE not set, returning all results without date filtering")

        # Fetch articles with date filtering via API
        all_articles = self._fetch_news(
            tickers=tickers,
            topics=topics,
            time_from=time_from,
            time_to=time_to,
            sort="LATEST",
        )

        print(f"Found {len(all_articles)} articles after API filtering")
        return all_articles


mcp = FastMCP("Search")


@mcp.tool()
def get_market_news(
    query: str,
    tickers: Optional[str] = None,
    topics: Optional[str] = None
) -> str:
    """
    Use Alpha Vantage NEWS_SENTIMENT API to retrieve market news articles with strict date filtering.
    Only returns articles published before TODAY_DATE (as configured in runtime config).

    Args:
        query: Search query description (used for logging purposes)
        tickers: Optional. Stock/crypto/forex symbols to filter by. 
                Examples: "AAPL" or "COIN,CRYPTO:BTC,FOREX:USD"
        topics: Optional. News topics to filter by.
                Examples: "technology" or "technology,ipo"
                Supported topics: blockchain, earnings, ipo, mergers_and_acquisitions,
                financial_markets, economy_fiscal, economy_monetary, economy_macro,
                energy_transportation, finance, life_sciences, manufacturing,
                real_estate, retail_wholesale, technology

    Returns:
        A string containing structured news articles with:
        - Title: Article title
        - URL: Article URL
        - Summary: Article summary
    """
    try:
        tool = AlphaVantageNewsTool()
        results = tool(query=query, tickers=tickers, topics=topics)

        # Check if results are empty
        if not results:
            return f"⚠️ No news articles found matching criteria '{query}' (tickers={tickers}, topics={topics}). Articles may have been filtered out by date restrictions."

        # Convert results to string format
        formatted_results = []
        for article in results:
            title = article.get("title", "N/A")
            url = article.get("url", "N/A")
            summary = article.get("summary", "N/A")
            time_published = article.get("time_published", "unknown")
            source = article.get("source", "N/A")
            
            # Format sentiment information
            overall_sentiment = article.get("overall_sentiment_score", "N/A")
            sentiment_label = article.get("overall_sentiment_label", "N/A")
            
            # Format ticker sentiment
            ticker_sentiment_str = "N/A"
            ticker_sentiment = article.get("ticker_sentiment", [])
            if ticker_sentiment:
                ticker_parts = []
                for ticker_info in ticker_sentiment:
                    ticker = ticker_info.get("ticker", "N/A")
                    relevance = ticker_info.get("relevance_score", "N/A")
                    sentiment_score = ticker_info.get("ticker_sentiment_score", "N/A")
                    sentiment_label_ticker = ticker_info.get("ticker_sentiment_label", "N/A")
                    ticker_parts.append(
                        f"{ticker}: relevance={relevance}, sentiment={sentiment_score} ({sentiment_label_ticker})"
                    )
                ticker_sentiment_str = "; ".join(ticker_parts)
            
            # Format topics
            topics_str = "N/A"
            topics_list = article.get("topics", [])
            if topics_list:
                topics_str = ", ".join([topic.get("topic", "") for topic in topics_list])

            formatted_result = f"""Title: {title}
Summary: {summary[:1000]}
--------------------------------"""

# Time Published: {time_published}
# Source: {source}
# Overall Sentiment: {sentiment_label} (score: {overall_sentiment})
# Ticker Sentiment: {ticker_sentiment_str}
# Topics: {topics_str}
            formatted_results.append(formatted_result)

        if not formatted_results:
            return f"⚠️ No news articles found matching criteria '{query}' after date filtering."

        return "\n".join(formatted_results)

    except Exception as e:
        logger.error(f"Alpha Vantage news tool execution failed: {str(e)}")
        return f"❌ Alpha Vantage news tool execution failed: {str(e)}"


if __name__ == "__main__":
    # Run with streamable-http, support configuring host and port through environment variables to avoid conflicts
    print("Running Alpha Vantage News Tool as search tool")
    port = int(os.getenv("SEARCH_HTTP_PORT", "8001"))
    mcp.run(transport="streamable-http", port=port)

    # results = get_market_news(query="AAPL", tickers="AAPL", topics="technology")
    # print(results)
