# /// script
# requires-python = ">=3.13"
# dependencies = ["httpx"]
# ///
"""Send a push notification via ntfy.sh."""

import httpx

try:
    from haiku_skills_notifications.notifications.scripts.ntfy import (
        auth_headers,
        resolve_server,
    )
# Fallback for standalone execution (sys.path[0] = script dir)
except ImportError:  # pragma: no cover
    from ntfy import auth_headers, resolve_server  # type: ignore[no-redef]


def main(
    topic: str,
    message: str,
    title: str = "",
    priority: str = "default",
    server: str = "",
) -> str:
    """Send a push notification to an ntfy.sh topic.

    Args:
        topic: The ntfy topic to publish to.
        message: The notification message body.
        title: Optional notification title.
        priority: Notification priority (1-5 or min/low/default/high/max).
        server: ntfy server URL (defaults to NTFY_SERVER env var or https://ntfy.sh).
    """
    base = resolve_server(server)
    url = f"{base}/{topic}"

    headers: dict[str, str] = {}
    if title:
        headers["X-Title"] = title
    if priority and priority != "default":
        headers["X-Priority"] = priority
    headers.update(auth_headers())

    try:
        response = httpx.post(url, content=message, headers=headers)
        response.raise_for_status()
    except httpx.HTTPError as e:
        return f"Error: {e}"

    return f"Notification sent to topic '{topic}'."


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Send a push notification via ntfy.sh."
    )
    parser.add_argument("--topic", required=True, help="The ntfy topic to publish to.")
    parser.add_argument(
        "--message", required=True, help="The notification message body."
    )
    parser.add_argument("--title", default="", help="Optional notification title.")
    parser.add_argument(
        "--priority",
        default="default",
        help="Notification priority (1-5 or min/low/default/high/max).",
    )
    parser.add_argument(
        "--server", default="", help="ntfy server URL (defaults to https://ntfy.sh)."
    )
    args = parser.parse_args()
    print(main(args.topic, args.message, args.title, args.priority, args.server))
