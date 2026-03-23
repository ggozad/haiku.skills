"""List Gmail draft emails."""

from typing import Any

from haiku_skills_gmail._auth import _get_service
from haiku_skills_gmail._helpers import _get_header


def _list_drafts(max_results: int = 10) -> list[dict[str, Any]]:
    """List draft emails and return raw draft dicts.

    Args:
        max_results: Maximum number of drafts to return.

    Returns:
        List of dicts with keys: draft_id, message_id, subject, to.
    """
    service = _get_service()
    response = (
        service.users().drafts().list(userId="me", maxResults=max_results).execute()
    )

    drafts = response.get("drafts", [])
    if not drafts:
        return []

    results = []
    for draft_ref in drafts:
        try:
            draft = (
                service.users()
                .drafts()
                .get(userId="me", id=draft_ref["id"], format="metadata")
                .execute()
            )
            msg = draft.get("message", {})
            headers = msg.get("payload", {}).get("headers", [])
            results.append(
                {
                    "draft_id": draft["id"],
                    "message_id": msg.get("id", ""),
                    "subject": _get_header(headers, "Subject"),
                    "to": _get_header(headers, "To"),
                }
            )
        except Exception:
            continue

    return results
