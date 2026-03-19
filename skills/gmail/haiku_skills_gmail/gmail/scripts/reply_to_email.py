# /// script
# requires-python = ">=3.13"
# dependencies = ["google-api-python-client", "google-auth", "google-auth-oauthlib"]
# ///
"""Reply to a Gmail email."""

from typing import Any

try:
    from haiku_skills_gmail.gmail.scripts.auth import _get_service
    from haiku_skills_gmail.gmail.scripts.helpers import (
        _build_message,
        _get_header,
    )
# Fallback for standalone execution (sys.path[0] = script dir)
except ImportError:  # pragma: no cover
    from auth import _get_service  # type: ignore[no-redef]
    from helpers import _build_message, _get_header  # type: ignore[no-redef]


def _reply_to_email(
    message_id: str,
    body: str,
    reply_all: bool = False,
) -> dict[str, Any]:
    """Reply to an email and return the API response.

    Args:
        message_id: The Gmail message ID to reply to.
        body: Reply body text.
        reply_all: If True, reply to all recipients.

    Returns:
        Dict with keys: id, threadId, subject, to.
    """
    service = _get_service()
    original = (
        service.users()
        .messages()
        .get(userId="me", id=message_id, format="metadata")
        .execute()
    )

    headers = original.get("payload", {}).get("headers", [])
    orig_subject = _get_header(headers, "Subject")
    orig_from = _get_header(headers, "From")
    orig_message_id = _get_header(headers, "Message-ID")
    thread_id = original.get("threadId", "")

    subject = orig_subject if orig_subject.startswith("Re: ") else f"Re: {orig_subject}"

    to = orig_from
    cc = ""
    if reply_all:
        profile = service.users().getProfile(userId="me").execute()
        my_email = profile.get("emailAddress", "")
        orig_to = _get_header(headers, "To")
        orig_cc = _get_header(headers, "Cc")
        cc_parts = [
            p.strip()
            for p in f"{orig_to}, {orig_cc}".split(",")
            if p.strip() and my_email not in p
        ]
        cc = ", ".join(cc_parts)

    message = _build_message(
        to=to,
        subject=subject,
        body=body,
        cc=cc,
        in_reply_to=orig_message_id,
        references=orig_message_id,
    )
    message["threadId"] = thread_id

    result = service.users().messages().send(userId="me", body=message).execute()
    return {**result, "subject": subject, "to": to, "threadId": thread_id}


def main(
    message_id: str,
    body: str,
    reply_all: bool = False,
) -> str:
    """Reply to an email.

    Args:
        message_id: The Gmail message ID to reply to.
        body: Reply body text.
        reply_all: If True, reply to all recipients.
    """
    try:
        result = _reply_to_email(message_id, body, reply_all)
    except Exception as e:
        return f"Error: {e}"

    return f"Reply sent successfully. Message ID: {result['id']}"


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Reply to a Gmail email.")
    parser.add_argument(
        "--message-id", required=True, help="The Gmail message ID to reply to."
    )
    parser.add_argument("--body", required=True, help="Reply body text.")
    parser.add_argument(
        "--reply-all",
        action="store_true",
        default=False,
        help="Reply to all recipients.",
    )
    args = parser.parse_args()
    print(main(args.message_id, args.body, args.reply_all))
