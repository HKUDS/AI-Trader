import logging
import os
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv()
import json
import os
import random
import re
import sys
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.general_tools import get_config_value

logger = logging.getLogger(__name__)


def parse_date_to_standard(date_str: str) -> str:
    """
    Convert various date formats to standard format (YYYY-MM-DD HH:MM:SS)

    Args:
        date_str: Date string in various formats, such as "2025-10-01T08:19:28+00:00", "4 hours ago", "1 day ago", "May 31, 2025"

    Returns:
        Standard format datetime string, such as "2025-10-01 08:19:28"
    """
    if not date_str or date_str == "unknown":
        return "unknown"

    # Handle relative time formats
    if "ago" in date_str.lower():
        try:
            now = datetime.now()
            if "hour" in date_str.lower():
                hours = int(re.findall(r"\d+", date_str)[0])
                target_date = now - timedelta(hours=hours)
            elif "day" in date_str.lower():
                days = int(re.findall(r"\d+", date_str)[0])
                target_date = now - timedelta(days=days)
            elif "week" in date_str.lower():
                weeks = int(re.findall(r"\d+", date_str)[0])
                target_date = now - timedelta(weeks=weeks)
            elif "month" in date_str.lower():
                months = int(re.findall(r"\d+", date_str)[0])
                target_date = now - timedelta(days=months * 30)  # Approximate handling
            else:
                return "unknown"
            return target_date.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass

    # Handle ISO 8601 format, such as "2025-10-01T08:19:28+00:00"
    try:
        if "T" in date_str and ("+" in date_str or "Z" in date_str or date_str.endswith("00:00")):
            # Remove timezone information, keep only date and time part
            if "+" in date_str:
                date_part = date_str.split("+")[0]
            elif "Z" in date_str:
                date_part = date_str.replace("Z", "")
            else:
                date_part = date_str

            # Parse ISO format
            if "." in date_part:
                # Handle microseconds part, such as "2025-10-01T08:19:28.123456"
                parsed_date = datetime.strptime(date_part.split(".")[0], "%Y-%m-%dT%H:%M:%S")
            else:
                # Standard ISO format "2025-10-01T08:19:28"
                parsed_date = datetime.strptime(date_part, "%Y-%m-%dT%H:%M:%S")
            return parsed_date.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass

    # Handle other common formats
    try:
        # Handle "May 31, 2025" format
        if "," in date_str and len(date_str.split()) >= 3:
            parsed_date = datetime.strptime(date_str, "%b %d, %Y")
            return parsed_date.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass

    try:
        # Handle "2025-10-01" format
        if re.match(r"\d{4}-\d{2}-\d{2}$", date_str):
            parsed_date = datetime.strptime(date_str, "%Y-%m-%d")
            return parsed_date.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass

    # If unable to parse, return original string
    return date_str


class WebScrapingJinaTool:
    def __init__(self):
        self.api_key = os.environ.get("JINA_API_KEY")
        if not self.api_key:
            raise ValueError("Jina API key not provided! Please set JINA_API_KEY environment variable.")

    def __call__(self, query: str) -> List[Dict[str, Any]]:
        print(f"Searching for {query}")
        all_urls = self._jina_search(query)
        return_content = []
        print(f"Found {len(all_urls)} URLs")
        if len(all_urls) > 1:
            # Randomly select three to form new all_urls
            all_urls = random.sample(all_urls, 1)
        for url in all_urls:
            print(f"Scraping {url}")
            return_content.append(self._jina_scrape(url))
            print(f"Scraped {url}")

        return return_content

    def _jina_scrape(self, url: str) -> Dict[str, Any]:
        try:
            jina_url = f"https://r.jina.ai/{url}"
            headers = {
                "Accept": "application/json",
                "Authorization": self.api_key,
                "X-Timeout": "10",
                "X-With-Generated-Alt": "true",
            }
            response = requests.get(jina_url, headers=headers)

            if response.status_code != 200:
                raise Exception(f"Jina AI Reader Failed for {url}: {response.status_code}")

            response_dict = response.json()

            return {
                "url": response_dict["data"]["url"],
                "title": response_dict["data"]["title"],
                "description": response_dict["data"]["description"],
                "content": response_dict["data"]["content"],
                "publish_time": response_dict["data"].get("publishedTime", "unknown"),
            }

        except Exception as e:
            logger.error(str(e))
            return {"url": url, "content": "", "error": str(e)}

    def _jina_search(self, query: str) -> List[str]:
        url = f"https://s.jina.ai/?q={query}&n=1"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "X-Respond-With": "no-content",
        }

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()  # 检查HTTP状态码

            json_data = response.json()

            # Check if response data is valid
            if json_data is None:
                print(f"⚠️ Jina API returned empty data, query: {query}")
                return []

            if "data" not in json_data:
                print(f"⚠️ Jina API response format abnormal, query: {query}, response: {json_data}")
                return []

            all_urls = []
            filtered_urls = []

            # Process search results, filter out content from TODAY_DATE and later
            for item in json_data.get("data", []):
                if "url" not in item:
                    continue

                # Get publication date and convert to standard format
                raw_date = item.get("date", "unknown")
                standardized_date = parse_date_to_standard(raw_date)

                # If unable to parse date, keep this result
                if standardized_date == "unknown" or standardized_date == raw_date:
                    filtered_urls.append(item["url"])
                    continue

                # Check if before TODAY_DATE
                today_date = get_config_value("TODAY_DATE")
                if today_date:
                    if today_date > standardized_date:
                        filtered_urls.append(item["url"])
                else:
                    # If TODAY_DATE is not set, keep all results
                    filtered_urls.append(item["url"])

            print(f"Found {len(filtered_urls)} URLs after filtering")
            return filtered_urls

        except requests.exceptions.RequestException as e:
            print(f"❌ Jina API request failed: {e}")
            return []
        except ValueError as e:
            print(f"❌ Jina API response parsing failed: {e}")
            return []
        except Exception as e:
            print(f"❌ Jina search unknown error: {e}")
            return []


mcp = FastMCP("Search")


@mcp.tool()
def get_information(query: str) -> str:
    """
    Use search tool to scrape and return main content information related to specified query in a structured way.

    Args:
        query: Key information or search terms you want to retrieve, will search for the most matching results on the internet.

    Returns:
        A string containing several retrieved web page contents, structured content includes:
        - URL: Original web page link
        - Title: Web page title
        - Description: Brief description of the web page
        - Publish Time: Content publication date (if available)
        - Content: Main text content of the web page (first 1000 characters)

        If scraping fails, returns corresponding error information.
    """
    try:
        tool = WebScrapingJinaTool()
        results = tool(query)

        # Check if results are empty
        if not results:
            return f"⚠️ Search query '{query}' found no results. May be network issue or API limitation."

        # Convert results to string format
        formatted_results = []
        for result in results:
            if "error" in result:
                formatted_results.append(f"Error: {result['error']}")
            else:
                formatted_results.append(
                    f"""
URL: {result['url']}
Title: {result['title']}
Description: {result['description']}
Publish Time: {result['publish_time']}
Content: {result['content'][:1000]}...
"""
                )

        if not formatted_results:
            return f"⚠️ Search query '{query}' returned empty results."
        

        # log_file = get_config_value("LOG_FILE")     
        # signature = get_config_value("SIGNATURE")
        # log_entry = {
        #     "signature": signature,
        #     "new_messages": [{"role": "tool:jinasearch", "content": "\n".join(formatted_results)}]
        # }
        # with open(log_file, "a", encoding="utf-8") as f:
        #     f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

        return "\n".join(formatted_results)

    except Exception as e:
        return f"❌ Search tool execution failed: {str(e)}"


if __name__ == "__main__":
    # Run with streamable-http, support configuring host and port through environment variables to avoid conflicts
    port = int(os.getenv("SEARCH_HTTP_PORT", "8001"))
    mcp.run(transport="streamable-http", port=port)
