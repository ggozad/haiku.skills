# /// script
# requires-python = ">=3.13"
# dependencies = ["httpx"]
# ///
"""Read cached messages from an ntfy.sh topic."""

import json
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


def _read(topic: str, since: str = "10m", server: str = "") -> list[dict[str, object]]:
    """Fetch and parse messages from an ntfy.sh topic.

    Returns:
        List of message dicts with keys: id, topic, message, title, priority, time.

    Raises:
        RuntimeError: On HTTP errors.
    """
    base = _resolve_server(server)
    url = f"{base}/{topic}/json"
    params = {"poll": "1", "since": since}
    headers = _auth_headers()

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


if __name__ == "__main__":
    topic = sys.argv[1]
    since = sys.argv[2] if len(sys.argv) > 2 else "10m"
    print(main(topic, since))
