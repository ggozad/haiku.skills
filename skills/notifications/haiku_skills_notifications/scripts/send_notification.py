# /// script
# requires-python = ">=3.13"
# dependencies = ["httpx"]
# ///
"""Send a push notification via ntfy.sh."""

import os
import sys

import httpx

DEFAULT_SERVER = "https://ntfy.sh"


def _resolve_server(server: str = "") -> str:
    return server or os.environ.get("NTFY_SERVER", "") or DEFAULT_SERVER


def _auth_headers() -> dict[str, str]:
    token = os.environ.get("NTFY_TOKEN", "")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


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
    base = _resolve_server(server)
    url = f"{base}/{topic}"

    headers: dict[str, str] = {}
    if title:
        headers["X-Title"] = title
    if priority and priority != "default":
        headers["X-Priority"] = priority
    headers.update(_auth_headers())

    try:
        response = httpx.post(url, content=message, headers=headers)
        response.raise_for_status()
    except httpx.HTTPError as e:
        return f"Error: {e}"

    return f"Notification sent to topic '{topic}'."


if __name__ == "__main__":
    topic = sys.argv[1]
    message = sys.argv[2]
    title = sys.argv[3] if len(sys.argv) > 3 else ""
    priority = sys.argv[4] if len(sys.argv) > 4 else "default"
    print(main(topic, message, title, priority))
