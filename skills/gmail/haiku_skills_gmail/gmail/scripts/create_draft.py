# /// script
# requires-python = ">=3.13"
# dependencies = ["google-api-python-client", "google-auth", "google-auth-oauthlib"]
# ///
"""Create a Gmail draft email."""

from typing import Any

try:
    from haiku_skills_gmail.gmail.scripts.auth import _get_service
    from haiku_skills_gmail.gmail.scripts.helpers import _build_message
# Fallback for standalone execution (sys.path[0] = script dir)
except ImportError:  # pragma: no cover
    from auth import _get_service  # type: ignore[no-redef]
    from helpers import _build_message  # type: ignore[no-redef]


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


def main(
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
) -> str:
    """Create a draft email.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Email body text.
        cc: CC recipients (comma-separated).
        bcc: BCC recipients (comma-separated).
    """
    try:
        result = _create_draft(to, subject, body, cc, bcc)
    except Exception as e:
        return f"Error: {e}"

    return f"Draft created successfully. Draft ID: {result['id']}"


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Create a Gmail draft.")
    parser.add_argument("--to", required=True, help="Recipient email address.")
    parser.add_argument("--subject", required=True, help="Email subject line.")
    parser.add_argument("--body", required=True, help="Email body text.")
    parser.add_argument("--cc", default="", help="CC recipients (comma-separated).")
    parser.add_argument("--bcc", default="", help="BCC recipients (comma-separated).")
    args = parser.parse_args()
    print(main(args.to, args.subject, args.body, args.cc, args.bcc))
