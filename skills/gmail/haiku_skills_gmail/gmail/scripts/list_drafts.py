# /// script
# requires-python = ">=3.13"
# dependencies = ["google-api-python-client", "google-auth", "google-auth-oauthlib"]
# ///
"""List Gmail draft emails."""

from typing import Any

try:
    from haiku_skills_gmail.gmail.scripts.auth import _get_service
    from haiku_skills_gmail.gmail.scripts.helpers import _get_header
# Fallback for standalone execution (sys.path[0] = script dir)
except ImportError:  # pragma: no cover
    from auth import _get_service  # type: ignore[no-redef]
    from helpers import _get_header  # type: ignore[no-redef]


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


def main(max_results: int = 10) -> str:
    """List existing draft emails.

    Args:
        max_results: Maximum number of drafts to return.
    """
    try:
        drafts = _list_drafts(max_results)
    except Exception as e:
        return f"Error: {e}"

    if not drafts:
        return "No drafts found."

    summaries = []
    for d in drafts:
        summaries.append(
            f"Draft ID: {d['draft_id']}\nTo: {d['to']}\nSubject: {d['subject']}"
        )
    return "\n\n---\n\n".join(summaries)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="List Gmail drafts.")
    parser.add_argument(
        "--max-results", type=int, default=10, help="Maximum number of drafts."
    )
    args = parser.parse_args()
    print(main(args.max_results))
