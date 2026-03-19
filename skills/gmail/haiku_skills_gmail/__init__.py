from pathlib import Path

from pydantic import BaseModel
from pydantic_ai import RunContext

from haiku.skills.models import Skill, SkillSource
from haiku.skills.parser import parse_skill_md
from haiku.skills.state import SkillRunDeps


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
    from haiku_skills_gmail.gmail.scripts.helpers import (
        _format_email_summary,
        _get_header,
    )
    from haiku_skills_gmail.gmail.scripts.search_emails import _search_emails

    try:
        results = _search_emails(query, max_results)
    except Exception as e:
        return f"Error: {e}"

    if not results:
        return f"No emails found for: {query}"

    summaries = []
    for msg in results:
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

    return "\n\n---\n\n".join(summaries)


def read_email(
    ctx: RunContext[SkillRunDeps],
    message_id: str,
) -> str:
    """Read the full content of an email.

    Args:
        message_id: The Gmail message ID.
    """
    from haiku_skills_gmail.gmail.scripts.read_email import _read_email

    try:
        email = _read_email(message_id)
    except Exception as e:
        return f"Error: {e}"

    if ctx.deps and ctx.deps.state and isinstance(ctx.deps.state, EmailState):
        ctx.deps.state.read_emails[message_id] = email["subject"]

    return (
        f"From: {email['sender']}\n"
        f"Subject: {email['subject']}\n"
        f"Date: {email['date']}\n\n"
        f"{email['body']}"
    )


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
    from haiku_skills_gmail.gmail.scripts.send_email import _send_email

    try:
        result = _send_email(to, subject, body, cc, bcc)
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
    from haiku_skills_gmail.gmail.scripts.reply_to_email import _reply_to_email

    try:
        result = _reply_to_email(message_id, body, reply_all)
    except Exception as e:
        return f"Error: {e}"

    msg_id = result["id"]
    thread_id = result["threadId"]
    to = result["to"]
    subject = result["subject"]

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
    from haiku_skills_gmail.gmail.scripts.create_draft import _create_draft

    try:
        result = _create_draft(to, subject, body, cc, bcc)
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
    from haiku_skills_gmail.gmail.scripts.list_drafts import main

    return main(max_results)


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
    from haiku_skills_gmail.gmail.scripts.modify_labels import _modify_labels

    try:
        return _modify_labels(message_id, add_labels, remove_labels)
    except Exception as e:
        return f"Error: {e}"


def list_labels(
    ctx: RunContext[SkillRunDeps],
) -> str:
    """List all available Gmail labels."""
    from haiku_skills_gmail.gmail.scripts.list_labels import main

    return main()


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
