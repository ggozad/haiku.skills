"""Search Gmail for emails matching a query."""

from typing import Any

from haiku_skills_gmail._auth import _get_service


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
