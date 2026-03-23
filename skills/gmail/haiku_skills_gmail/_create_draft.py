"""Create a Gmail draft email."""

from typing import Any

from haiku_skills_gmail._auth import _get_service
from haiku_skills_gmail._helpers import _build_message


def _create_draft(
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
) -> dict[str, Any]:
    """Create a draft email and return the API response.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Email body text.
        cc: CC recipients (comma-separated).
        bcc: BCC recipients (comma-separated).

    Returns:
        Dict with keys: id, message.
    """
    service = _get_service()
    message = _build_message(to=to, subject=subject, body=body, cc=cc, bcc=bcc)
    return (
        service.users()
        .drafts()
        .create(userId="me", body={"message": message})
        .execute()
    )
