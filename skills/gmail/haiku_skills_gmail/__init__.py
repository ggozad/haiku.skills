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
from pydantic_ai import RunContext

from haiku.skills.models import Skill, SkillSource
from haiku.skills.parser import parse_skill_md
from haiku.skills.state import SkillRunDeps

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


def search_emails(
    ctx: RunContext[SkillRunDeps],
    query: str,
    max_results: int = 10,
) -> str:
    """Search Gmail for emails matching a query.

    Args:
        query: Gmail search query (e.g. "from:alice subject:meeting").
        max_results: Maximum number of results to return.
    """
    try:
        service = _get_service()
        response = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )
    except Exception as e:
        return f"Error: {e}"

    messages = response.get("messages", [])
    if not messages:
        return f"No emails found for: {query}"

    summaries = []
    for msg_ref in messages:
        try:
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=msg_ref["id"], format="metadata")
                .execute()
            )
            summaries.append(_format_email_summary(msg))

            if ctx.deps and ctx.deps.state and isinstance(ctx.deps.state, EmailState):
                headers = msg.get("payload", {}).get("headers", [])
                ctx.deps.state.searches.setdefault(query, []).append(
                    EmailSummary(
                        message_id=msg["id"],
                        thread_id=msg["threadId"],
                        subject=_get_header(headers, "Subject"),
                        sender=_get_header(headers, "From"),
                        snippet=msg.get("snippet", ""),
                    )
                )
        except Exception:
            continue

    if not summaries:
        return f"No emails found for: {query}"

    return "\n\n---\n\n".join(summaries)


def read_email(
    ctx: RunContext[SkillRunDeps],
    message_id: str,
) -> str:
    """Read the full content of an email.

    Args:
        message_id: The Gmail message ID.
    """
    try:
        service = _get_service()
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
    except Exception as e:
        return f"Error: {e}"

    headers = msg.get("payload", {}).get("headers", [])
    subject = _get_header(headers, "Subject")
    sender = _get_header(headers, "From")
    date = _get_header(headers, "Date")
    body = _parse_email_body(msg.get("payload", {}))

    if ctx.deps and ctx.deps.state and isinstance(ctx.deps.state, EmailState):
        ctx.deps.state.read_emails[message_id] = subject

    return f"From: {sender}\nSubject: {subject}\nDate: {date}\n\n{body}"


def send_email(
    ctx: RunContext[SkillRunDeps],
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
) -> str:
    """Send a new email.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Email body text.
        cc: CC recipients (comma-separated).
        bcc: BCC recipients (comma-separated).
    """
    try:
        service = _get_service()
        message = _build_message(to=to, subject=subject, body=body, cc=cc, bcc=bcc)
        result = service.users().messages().send(userId="me", body=message).execute()
    except Exception as e:
        return f"Error: {e}"

    msg_id = result["id"]
    thread_id = result["threadId"]

    if ctx.deps and ctx.deps.state and isinstance(ctx.deps.state, EmailState):
        ctx.deps.state.sent_emails.append(
            SentEmail(
                message_id=msg_id,
                thread_id=thread_id,
                to=to,
                subject=subject,
            )
        )

    return f"Email sent successfully. Message ID: {msg_id}"


def reply_to_email(
    ctx: RunContext[SkillRunDeps],
    message_id: str,
    body: str,
    reply_all: bool = False,
) -> str:
    """Reply to an email.

    Args:
        message_id: The Gmail message ID to reply to.
        body: Reply body text.
        reply_all: If True, reply to all recipients.
    """
    try:
        service = _get_service()
        original = (
            service.users()
            .messages()
            .get(userId="me", id=message_id, format="metadata")
            .execute()
        )
    except Exception as e:
        return f"Error: {e}"

    headers = original.get("payload", {}).get("headers", [])
    orig_subject = _get_header(headers, "Subject")
    orig_from = _get_header(headers, "From")
    orig_message_id = _get_header(headers, "Message-ID")
    thread_id = original.get("threadId", "")

    subject = orig_subject if orig_subject.startswith("Re: ") else f"Re: {orig_subject}"

    to = orig_from
    cc = ""
    if reply_all:
        orig_to = _get_header(headers, "To")
        orig_cc = _get_header(headers, "Cc")
        cc_parts = [p.strip() for p in f"{orig_to}, {orig_cc}".split(",") if p.strip()]
        cc = ", ".join(cc_parts)

    message = _build_message(
        to=to,
        subject=subject,
        body=body,
        cc=cc,
        in_reply_to=orig_message_id,
        references=orig_message_id,
    )
    message["threadId"] = thread_id

    try:
        result = service.users().messages().send(userId="me", body=message).execute()
    except Exception as e:
        return f"Error: {e}"

    msg_id = result["id"]

    if ctx.deps and ctx.deps.state and isinstance(ctx.deps.state, EmailState):
        ctx.deps.state.sent_emails.append(
            SentEmail(
                message_id=msg_id,
                thread_id=thread_id,
                to=to,
                subject=subject,
            )
        )

    return f"Reply sent successfully. Message ID: {msg_id}"


def create_draft(
    ctx: RunContext[SkillRunDeps],
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
) -> str:
    """Create a draft email.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Email body text.
        cc: CC recipients (comma-separated).
        bcc: BCC recipients (comma-separated).
    """
    try:
        service = _get_service()
        message = _build_message(to=to, subject=subject, body=body, cc=cc, bcc=bcc)
        result = (
            service.users()
            .drafts()
            .create(userId="me", body={"message": message})
            .execute()
        )
    except Exception as e:
        return f"Error: {e}"

    draft_id = result["id"]
    msg_id = result.get("message", {}).get("id", "")

    if ctx.deps and ctx.deps.state and isinstance(ctx.deps.state, EmailState):
        ctx.deps.state.drafts.append(
            DraftSummary(
                draft_id=draft_id,
                message_id=msg_id,
                subject=subject,
                to=to,
            )
        )

    return f"Draft created successfully. Draft ID: {draft_id}"


def list_drafts(
    ctx: RunContext[SkillRunDeps],
    max_results: int = 10,
) -> str:
    """List existing draft emails.

    Args:
        max_results: Maximum number of drafts to return.
    """
    try:
        service = _get_service()
        response = (
            service.users().drafts().list(userId="me", maxResults=max_results).execute()
        )
    except Exception as e:
        return f"Error: {e}"

    drafts = response.get("drafts", [])
    if not drafts:
        return "No drafts found."

    summaries = []
    for draft_ref in drafts:
        try:
            draft = (
                service.users()
                .drafts()
                .get(userId="me", id=draft_ref["id"], format="metadata")
                .execute()
            )
            msg = draft.get("message", {})
            headers = msg.get("payload", {}).get("headers", [])
            subject = _get_header(headers, "Subject")
            to = _get_header(headers, "To")
            summaries.append(f"Draft ID: {draft['id']}\nTo: {to}\nSubject: {subject}")
        except Exception:
            continue

    if not summaries:
        return "No drafts found."

    return "\n\n---\n\n".join(summaries)


def modify_labels(
    ctx: RunContext[SkillRunDeps],
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
    add_list = [label.strip() for label in add_labels.split(",") if label.strip()]
    remove_list = [label.strip() for label in remove_labels.split(",") if label.strip()]

    try:
        service = _get_service()
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={
                "addLabelIds": add_list,
                "removeLabelIds": remove_list,
            },
        ).execute()
    except Exception as e:
        return f"Error: {e}"

    parts = []
    if add_list:
        parts.append(f"added [{', '.join(add_list)}]")
    if remove_list:
        parts.append(f"removed [{', '.join(remove_list)}]")

    return f"Labels updated for message {message_id}: {', '.join(parts)}."


def list_labels(
    ctx: RunContext[SkillRunDeps],
) -> str:
    """List all available Gmail labels."""
    try:
        service = _get_service()
        response = service.users().labels().list(userId="me").execute()
    except Exception as e:
        return f"Error: {e}"

    labels = response.get("labels", [])
    lines = []
    for label in labels:
        name = label.get("name", "")
        label_type = label.get("type", "")
        lines.append(f"- {name} ({label_type})")

    return "\n".join(lines)


def create_skill() -> Skill:
    skill_dir = Path(__file__).parent / "gmail"
    metadata, instructions = parse_skill_md(skill_dir / "SKILL.md")

    return Skill(
        metadata=metadata,
        source=SkillSource.ENTRYPOINT,
        path=skill_dir,
        instructions=instructions,
        tools=[
            search_emails,
            read_email,
            send_email,
            reply_to_email,
            create_draft,
            list_drafts,
            modify_labels,
            list_labels,
        ],
        state_type=EmailState,
        state_namespace="gmail",
    )
