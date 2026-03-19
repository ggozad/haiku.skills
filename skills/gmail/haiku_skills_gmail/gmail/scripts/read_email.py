# /// script
# requires-python = ">=3.13"
# dependencies = ["google-api-python-client", "google-auth", "google-auth-oauthlib"]
# ///
"""Read the full content of a Gmail email."""

from typing import Any

try:
    from haiku_skills_gmail.gmail.scripts.auth import _get_service
    from haiku_skills_gmail.gmail.scripts.helpers import (
        _get_header,
        _parse_email_body,
    )
# Fallback for standalone execution (sys.path[0] = script dir)
except ImportError:  # pragma: no cover
    from auth import _get_service  # type: ignore[no-redef]
    from helpers import _get_header, _parse_email_body  # type: ignore[no-redef]


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


def main(message_id: str) -> str:
    """Read the full content of an email.

    Args:
        message_id: The Gmail message ID.
    """
    try:
        email = _read_email(message_id)
    except Exception as e:
        return f"Error: {e}"

    return (
        f"From: {email['sender']}\n"
        f"Subject: {email['subject']}\n"
        f"Date: {email['date']}\n\n"
        f"{email['body']}"
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Read a Gmail email.")
    parser.add_argument("--message-id", required=True, help="The Gmail message ID.")
    args = parser.parse_args()
    print(main(args.message_id))
