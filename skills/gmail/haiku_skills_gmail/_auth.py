"""Gmail OAuth2 authentication utilities."""

import os
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

_service: Any = None


def _credentials_path() -> Path:
    env = os.environ.get("EMAIL_CREDENTIALS_PATH")
    if env:
        return Path(env)
    return Path.home() / ".config" / "haiku-skills-gmail" / "credentials.json"


def _token_path() -> Path:
    env = os.environ.get("EMAIL_TOKEN_PATH")
    if env:
        return Path(env)
    return Path.home() / ".config" / "haiku-skills-gmail" / "token.json"


def _get_service() -> Any:
    global _service
    if _service is not None:
        return _service

    creds_path = _credentials_path()
    token_path = _token_path()

    if not creds_path.exists():
        raise FileNotFoundError(
            f"credentials.json not found at {creds_path}. "
            "Download OAuth2 credentials from Google Cloud Console."
        )

    creds: Any = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds and not creds.valid and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_text(creds.to_json())
        except Exception:
            creds = None

    if not (creds and creds.valid):
        flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
        creds = flow.run_local_server(port=0)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json())

    _service = build("gmail", "v1", credentials=creds)
    return _service
