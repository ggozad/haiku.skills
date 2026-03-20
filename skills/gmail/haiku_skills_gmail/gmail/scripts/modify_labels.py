# /// script
# requires-python = ">=3.13"
# dependencies = ["google-api-python-client", "google-auth", "google-auth-oauthlib"]
# ///
"""Add or remove labels from a Gmail email."""

try:
    from haiku_skills_gmail.gmail.scripts.auth import _get_service
# Fallback for standalone execution (sys.path[0] = script dir)
except ImportError:  # pragma: no cover
    from auth import _get_service  # type: ignore[no-redef]


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


def main(
    message_id: str,
    add_labels: str = "",
    remove_labels: str = "",
) -> str:
    """Add or remove labels from an email.

    Args:
        message_id: The Gmail message ID.
        add_labels: Comma-separated label IDs to add.
        remove_labels: Comma-separated label IDs to remove.
    """
    try:
        return _modify_labels(message_id, add_labels, remove_labels)
    except Exception as e:
        return f"Error: {e}"


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Modify Gmail email labels.")
    parser.add_argument("--message-id", required=True, help="The Gmail message ID.")
    parser.add_argument(
        "--add-labels", default="", help="Comma-separated label IDs to add."
    )
    parser.add_argument(
        "--remove-labels", default="", help="Comma-separated label IDs to remove."
    )
    args = parser.parse_args()
    print(main(args.message_id, args.add_labels, args.remove_labels))
