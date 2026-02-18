# /// script
# requires-python = ">=3.13"
# dependencies = ["httpx"]
# ///
"""Search the web using Brave Search API."""

import json
import os
import sys

import httpx


def _search(query: str, count: int = 5) -> list[dict[str, str]]:
    """Execute a Brave Search API request and return raw result dicts.

    Args:
        query: The search query.
        count: Number of results to return.

    Returns:
        List of dicts with 'title', 'url', and 'description' keys.

    Raises:
        RuntimeError: If BRAVE_API_KEY is not set.
    """
    api_key = os.environ.get("BRAVE_API_KEY", "")
    if not api_key:
        raise RuntimeError("BRAVE_API_KEY not set.")

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

    return [
        {
            "title": item["title"],
            "url": item["url"],
            "description": item.get("description", ""),
        }
        for item in data.get("web", {}).get("results", [])
    ]


def main(query: str, count: int = 5) -> str:
    """Search the web using Brave Search.

    Args:
        query: The search query.
        count: Number of results to return.
    """
    try:
        results = _search(query, count)
    except RuntimeError as e:
        return f"Error: {e}"

    formatted = []
    for item in results:
        formatted.append(
            f"**{item['title']}**\n{item['description']}\nURL: {item['url']}"
        )

    return "\n\n---\n\n".join(formatted) if formatted else "No results found."


if __name__ == "__main__":
    args = json.loads(sys.stdin.read())
    print(json.dumps({"result": main(**args)}))
