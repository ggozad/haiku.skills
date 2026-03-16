from pathlib import Path

from pydantic import BaseModel
from pydantic_ai import RunContext

from haiku.skills.models import Skill, SkillSource
from haiku.skills.parser import parse_skill_md
from haiku.skills.state import SkillRunDeps


class SentMessage(BaseModel):
    topic: str
    message: str
    title: str = ""
    priority: str = "default"


class ReceivedMessage(BaseModel):
    id: str
    topic: str
    message: str
    title: str = ""
    priority: int = 3
    time: int = 0


class NotificationState(BaseModel):
    sent: list[SentMessage] = []
    received: list[ReceivedMessage] = []


def send_notification(
    ctx: RunContext[SkillRunDeps],
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
    from haiku_skills_notifications.scripts.send_notification import main

    result = main(topic, message, title, priority, server)

    if (
        ctx.deps
        and ctx.deps.state
        and isinstance(ctx.deps.state, NotificationState)
        and not result.startswith("Error:")
    ):
        ctx.deps.state.sent.append(
            SentMessage(topic=topic, message=message, title=title, priority=priority)
        )

    return result


def read_notifications(
    ctx: RunContext[SkillRunDeps],
    topic: str,
    since: str = "10m",
    server: str = "",
) -> str:
    """Read cached messages from an ntfy.sh topic.

    Args:
        topic: The ntfy topic to read from.
        since: How far back to look (e.g. "10m", "1h", "all").
        server: ntfy server URL (defaults to NTFY_SERVER env var or https://ntfy.sh).
    """
    from haiku_skills_notifications.scripts.read_notifications import _read

    try:
        raw = _read(topic, since, server)
    except Exception as e:
        return f"Error: {e}"

    if ctx.deps and ctx.deps.state and isinstance(ctx.deps.state, NotificationState):
        for msg in raw:
            ctx.deps.state.received.append(
                ReceivedMessage(
                    id=str(msg.get("id", "")),
                    topic=str(msg.get("topic", topic)),
                    message=str(msg.get("message", "")),
                    title=str(msg.get("title", "")),
                    priority=int(msg.get("priority", 3)),  # type: ignore[arg-type]
                    time=int(msg.get("time", 0)),  # type: ignore[arg-type]
                )
            )

    if not raw:
        return f"No messages on topic '{topic}'."

    formatted = []
    for msg in raw:
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


def create_skill() -> Skill:
    skill_dir = Path(__file__).parent / "notifications"
    metadata, instructions = parse_skill_md(skill_dir / "SKILL.md")

    return Skill(
        metadata=metadata,
        source=SkillSource.ENTRYPOINT,
        path=skill_dir,
        instructions=instructions,
        tools=[send_notification, read_notifications],
        state_type=NotificationState,
        state_namespace="notifications",
    )
