# /// script
# requires-python = ">=3.13"
# dependencies = ["trafilatura"]
# ///
"""Fetch a web page and extract its readable content."""

import json
import sys

import trafilatura
from trafilatura import extract


def main(url: str) -> str:
    """Fetch a web page and extract its main content as text.

    Args:
        url: The URL of the page to fetch.
    """
    downloaded = trafilatura.fetch_url(url)
    if downloaded is None:
        return "Error: could not fetch the page."

    content = extract(downloaded, include_links=True)
    if content is None:
        return "Error: could not extract content from the page."

    return content


if __name__ == "__main__":
    args = json.loads(sys.stdin.read())
    print(json.dumps({"result": main(**args)}))
