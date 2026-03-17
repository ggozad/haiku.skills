# /// script
# requires-python = ">=3.13"
# dependencies = ["httpx"]
# ///
"""Read cached messages from an ntfy.sh topic."""

import json
import sys
from typing import Any

import httpx

from haiku_skills_notifications.scripts.ntfy import auth_headers, resolve_server


def _read(topic: str, since: str = "10m", server: str = "") -> list[dict[str, Any]]:
    """Fetch and parse messages from an ntfy.sh topic.

    Returns:
        List of message dicts with keys: id, topic, message, title, priority, time.

    Raises:
        RuntimeError: On HTTP errors.
    """
    base = resolve_server(server)
    url = f"{base}/{topic}/json"
    params = {"poll": "1", "since": since}
    headers = auth_headers()

    response = httpx.get(url, params=params, headers=headers)
    response.raise_for_status()

    messages = []
    for line in response.text.strip().splitlines():
        if not line:
            continue
        event = json.loads(line)
        if event.get("event") != "message":
            continue
        messages.append(event)

    return messages


def format_messages(messages: list[dict[str, Any]]) -> str:
    """Format parsed ntfy messages for display."""
    formatted = []
    for msg in messages:
        parts = []
        title = msg.get("title", "")
        if title:
            parts.append(f"**{title}**")
        parts.append(str(msg.get("message", "")))
        priority = msg.get("priority", 3)
        if priority != 3:
            parts.append(f"(priority: {priority})")
        formatted.append("\n".join(parts))

    return "\n\n---\n\n".join(formatted)


def main(topic: str, since: str = "10m", server: str = "") -> str:
    """Read cached messages from an ntfy.sh topic.

    Args:
        topic: The ntfy topic to read from.
        since: How far back to look (e.g. "10m", "1h", "all").
        server: ntfy server URL (defaults to NTFY_SERVER env var or https://ntfy.sh).
    """
    try:
        messages = _read(topic, since, server)
    except (httpx.HTTPError, RuntimeError) as e:
        return f"Error: {e}"

    if not messages:
        return f"No messages on topic '{topic}'."

    return format_messages(messages)


if __name__ == "__main__":
    topic = sys.argv[1]
    since = sys.argv[2] if len(sys.argv) > 2 else "10m"
    print(main(topic, since))
