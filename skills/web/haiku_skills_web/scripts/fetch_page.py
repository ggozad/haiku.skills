# /// script
# requires-python = ">=3.13"
# dependencies = ["trafilatura"]
# ///
"""Fetch a web page and extract its readable content."""

import sys

from trafilatura import extract
from trafilatura.downloads import fetch_response


def _is_html(content_type: str) -> bool:
    return "html" in content_type or "xml" in content_type


def main(url: str) -> str:
    """Fetch a web page and extract its main content as text.

    Args:
        url: The URL of the page to fetch.
    """
    response = fetch_response(url, with_headers=True, decode=True)
    if response is None:
        return "Error: could not fetch the page."

    content_type = (response.headers or {}).get("content-type", "text/html")
    if not _is_html(content_type):
        return response.html or "Error: could not decode the response."

    content = extract(response.html, include_links=True)
    if content is None:
        return "Error: could not extract content from the page."

    return content


if __name__ == "__main__":
    print(main(sys.argv[1]))
