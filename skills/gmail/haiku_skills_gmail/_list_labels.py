"""List all available Gmail labels."""

from typing import Any

from haiku_skills_gmail._auth import _get_service


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
