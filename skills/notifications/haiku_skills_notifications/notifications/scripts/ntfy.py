"""Shared ntfy.sh utilities."""

import os

DEFAULT_SERVER = "https://ntfy.sh"


def resolve_server(server: str = "") -> str:
    return server or os.environ.get("NTFY_SERVER", "") or DEFAULT_SERVER


def auth_headers() -> dict[str, str]:
    token = os.environ.get("NTFY_TOKEN", "")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}
