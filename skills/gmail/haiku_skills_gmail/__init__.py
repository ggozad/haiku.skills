import base64
import os
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from pydantic import BaseModel

from haiku.skills.models import Skill, SkillSource
from haiku.skills.parser import parse_skill_md
from haiku.skills.state import SkillRunDeps  # noqa: F401

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

_service: Any = None


class EmailSummary(BaseModel):
    message_id: str
    thread_id: str
    subject: str
    sender: str
    snippet: str


class SentEmail(BaseModel):
    message_id: str
    thread_id: str
    to: str
    subject: str


class DraftSummary(BaseModel):
    draft_id: str
    message_id: str
    subject: str
    to: str


class EmailState(BaseModel):
    searches: dict[str, list[EmailSummary]] = {}
    read_emails: dict[str, str] = {}
    sent_emails: list[SentEmail] = []
    drafts: list[DraftSummary] = []


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

    if creds and creds.valid:
        pass
    elif creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
        creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json())

    _service = build("gmail", "v1", credentials=creds)
    return _service


def _get_header(headers: list[dict[str, str]], name: str) -> str:
    for header in headers:
        if header["name"] == name:
            return header["value"]
    return ""


def _parse_email_body(payload: dict[str, Any]) -> str:
    mime_type = payload.get("mimeType", "")

    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode()
        return ""

    if mime_type.startswith("multipart/"):
        for part in payload.get("parts", []):
            result = _parse_email_body(part)
            if result:
                return result

    return ""


def _build_message(
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
    in_reply_to: str = "",
    references: str = "",
) -> dict[str, str]:
    message = MIMEText(body)
    message["To"] = to
    message["Subject"] = subject
    if cc:
        message["Cc"] = cc
    if bcc:
        message["Bcc"] = bcc
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
    if references:
        message["References"] = references

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return {"raw": raw}


def _format_email_summary(msg: dict[str, Any]) -> str:
    headers = msg.get("payload", {}).get("headers", [])
    subject = _get_header(headers, "Subject")
    sender = _get_header(headers, "From")
    date = _get_header(headers, "Date")
    snippet = msg.get("snippet", "")
    msg_id = msg.get("id", "")

    return (
        f"ID: {msg_id}\n"
        f"From: {sender}\n"
        f"Subject: {subject}\n"
        f"Date: {date}\n"
        f"Snippet: {snippet}"
    )


def create_skill() -> Skill:
    skill_dir = Path(__file__).parent / "gmail"
    metadata, instructions = parse_skill_md(skill_dir / "SKILL.md")

    return Skill(
        metadata=metadata,
        source=SkillSource.ENTRYPOINT,
        path=skill_dir,
        instructions=instructions,
        tools=[],
        state_type=EmailState,
        state_namespace="gmail",
    )
