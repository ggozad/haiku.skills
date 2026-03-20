# /// script
# requires-python = ">=3.13"
# dependencies = ["google-api-python-client", "google-auth", "google-auth-oauthlib"]
# ///
"""List all available Gmail labels."""

from typing import Any

try:
    from haiku_skills_gmail.gmail.scripts.auth import _get_service
# Fallback for standalone execution (sys.path[0] = script dir)
except ImportError:  # pragma: no cover
    from auth import _get_service  # type: ignore[no-redef]


def _list_labels() -> list[dict[str, Any]]:
    """List all Gmail labels.

    Returns:
        List of dicts with keys: id, name, type.
    """
    service = _get_service()
    response = service.users().labels().list(userId="me").execute()

    return [
        {
            "id": label.get("id", ""),
            "name": label.get("name", ""),
            "type": label.get("type", ""),
        }
        for label in response.get("labels", [])
    ]


def main() -> str:
    """List all available Gmail labels."""
    try:
        labels = _list_labels()
    except Exception as e:
        return f"Error: {e}"

    lines = []
    for label in labels:
        lines.append(f"- {label['name']} ({label['type']})")

    return "\n".join(lines)


if __name__ == "__main__":
    print(main())
