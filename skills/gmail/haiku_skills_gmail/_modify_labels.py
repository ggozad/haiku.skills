"""Add or remove labels from a Gmail email."""

from haiku_skills_gmail._auth import _get_service


def _modify_labels(
    message_id: str,
    add_labels: str = "",
    remove_labels: str = "",
) -> str:
    """Modify labels on an email.

    Args:
        message_id: The Gmail message ID.
        add_labels: Comma-separated label IDs to add.
        remove_labels: Comma-separated label IDs to remove.

    Returns:
        Formatted result string.
    """
    add_list = [label.strip() for label in add_labels.split(",") if label.strip()]
    remove_list = [label.strip() for label in remove_labels.split(",") if label.strip()]

    service = _get_service()
    service.users().messages().modify(
        userId="me",
        id=message_id,
        body={
            "addLabelIds": add_list,
            "removeLabelIds": remove_list,
        },
    ).execute()

    parts = []
    if add_list:
        parts.append(f"added [{', '.join(add_list)}]")
    if remove_list:
        parts.append(f"removed [{', '.join(remove_list)}]")

    return f"Labels updated for message {message_id}: {', '.join(parts)}."
