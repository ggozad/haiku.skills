"""Send a push notification via ntfy.sh."""

import httpx

from haiku_skills_notifications._ntfy import auth_headers, resolve_server


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
