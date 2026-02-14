# /// script
# requires-python = ">=3.13"
# dependencies = ["httpx"]
# ///
"""Search the web using Brave Search API."""

import json
import os
import sys

import httpx


def main(query: str, count: int = 5) -> str:
    """Search the web using Brave Search.

    Args:
        query: The search query.
        count: Number of results to return.
    """
    api_key = os.environ.get("BRAVE_API_KEY", "")
    if not api_key:
        return "Error: BRAVE_API_KEY not set."

    response = httpx.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": count},
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": api_key,
        },
    )
    response.raise_for_status()
    data = response.json()

    results = []
    for item in data.get("web", {}).get("results", []):
        results.append(
            f"**{item['title']}**\n{item.get('description', '')}\nURL: {item['url']}"
        )

    return "\n\n---\n\n".join(results) if results else "No results found."


if __name__ == "__main__":
    args = json.loads(sys.stdin.read())
    print(json.dumps({"result": main(**args)}))
