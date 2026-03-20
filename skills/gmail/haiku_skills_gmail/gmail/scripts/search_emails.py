# /// script
# requires-python = ">=3.13"
# dependencies = ["google-api-python-client", "google-auth", "google-auth-oauthlib"]
# ///
"""Search Gmail for emails matching a query."""

from typing import Any

try:
    from haiku_skills_gmail.gmail.scripts.auth import _get_service
    from haiku_skills_gmail.gmail.scripts.helpers import _format_email_summary
# Fallback for standalone execution (sys.path[0] = script dir)
except ImportError:  # pragma: no cover
    from auth import _get_service  # type: ignore[no-redef]
    from helpers import _format_email_summary  # type: ignore[no-redef]


def _search_emails(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Search Gmail and return raw message dicts.

    Args:
        query: Gmail search query.
        max_results: Maximum number of results to return.

    Returns:
        List of full message dicts (metadata format).
    """
    service = _get_service()
    response = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=max_results)
        .execute()
    )

    messages = response.get("messages", [])
    if not messages:
        return []

    results = []
    for msg_ref in messages:
        try:
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=msg_ref["id"], format="metadata")
                .execute()
            )
            results.append(msg)
        except Exception:
            continue

    return results


def main(query: str, max_results: int = 10) -> str:
    """Search Gmail for emails matching a query.

    Args:
        query: Gmail search query (e.g. "from:alice subject:meeting").
        max_results: Maximum number of results to return.
    """
    try:
        results = _search_emails(query, max_results)
    except Exception as e:
        return f"Error: {e}"

    if not results:
        return f"No emails found for: {query}"

    return "\n\n---\n\n".join(_format_email_summary(msg) for msg in results)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Search Gmail for emails.")
    parser.add_argument("--query", required=True, help="Gmail search query.")
    parser.add_argument(
        "--max-results", type=int, default=10, help="Maximum number of results."
    )
    args = parser.parse_args()
    print(main(args.query, args.max_results))
