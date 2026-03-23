"""Read the full content of a Gmail email."""

from typing import Any

from haiku_skills_gmail._auth import _get_service
from haiku_skills_gmail._helpers import (
    _get_header,
    _parse_email_body,
)


def _read_email(message_id: str) -> dict[str, Any]:
    """Fetch a full email message.

    Args:
        message_id: The Gmail message ID.

    Returns:
        Dict with keys: subject, sender, date, body, thread_id.
    """
    service = _get_service()
    msg = (
        service.users()
        .messages()
        .get(userId="me", id=message_id, format="full")
        .execute()
    )

    headers = msg.get("payload", {}).get("headers", [])
    return {
        "subject": _get_header(headers, "Subject"),
        "sender": _get_header(headers, "From"),
        "date": _get_header(headers, "Date"),
        "body": _parse_email_body(msg.get("payload", {})),
        "thread_id": msg.get("threadId", ""),
    }
