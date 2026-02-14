# pragma: no cover
import re
from pathlib import Path
from typing import TYPE_CHECKING

from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Collapsible, LoadingIndicator, Markdown, Static

from haiku.skills.models import Task, TaskStatus

if TYPE_CHECKING:
    from textual.app import ComposeResult

_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")

try:
    from textual_image.widget import Image

    TEXTUAL_IMAGE_AVAILABLE = True
except ImportError:
    TEXTUAL_IMAGE_AVAILABLE = False


def _extract_images(content: str) -> tuple[str, list[str]]:
    """Extract image paths from markdown, returning cleaned text and paths."""
    paths = []
    for match in _IMAGE_RE.finditer(content):
        image_path = match.group(2)
        if Path(image_path).is_file():
            paths.append(image_path)
    text = _IMAGE_RE.sub("", content).strip() if paths else content
    return text, paths


class ChatMessage(Static):
    """A single chat message with role styling."""

    def __init__(self, role: str, content: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self.role = role
        self.content = content

    def compose(self) -> "ComposeResult":
        prefix = "**You:**" if self.role == "user" else "**Assistant:**"
        text, image_paths = _extract_images(str(self.content))
        yield Markdown(f"{prefix}\n\n{text}", id="message-content")
        if TEXTUAL_IMAGE_AVAILABLE:
            for path in image_paths:
                yield Image(path, classes="chat-image")

    def update_content(self, content: str) -> None:
        self.content = content
        prefix = "**You:**" if self.role == "user" else "**Assistant:**"
        text, image_paths = _extract_images(content)
        markdown = self.query_one("#message-content", Markdown)
        markdown.update(f"{prefix}\n\n{text}")
        if TEXTUAL_IMAGE_AVAILABLE:
            for widget in self.query(".chat-image"):
                widget.remove()
            for path in image_paths:
                self.mount(Image(path, classes="chat-image"))


class TaskWidget(Static):
    """Displays a single skill task with status indicator."""

    STATUS_ICONS = {
        TaskStatus.PENDING: "○",
        TaskStatus.IN_PROGRESS: "◌",
        TaskStatus.COMPLETED: "✓",
        TaskStatus.FAILED: "✗",
    }

    def __init__(self, task: Task, **kwargs) -> None:
        super().__init__(**kwargs)
        self.skill_task = task
        self._collapsed = True

    def compose(self) -> "ComposeResult":
        icon = self.STATUS_ICONS.get(self.skill_task.status, "?")
        skills = self.skill_task.skill
        with Horizontal(classes="task-row"):
            yield Static(icon, classes="task-status")
            yield Static(self.skill_task.description, classes="task-desc")
            yield Static(f"[{skills}]", classes="task-skills")
        if self.skill_task.result:
            text, image_paths = _extract_images(self.skill_task.result)
            with Collapsible(
                title=f"Result: {self.skill_task.description}",
                collapsed=self._collapsed,
                classes="task-result",
            ):
                yield Markdown(text)
                if TEXTUAL_IMAGE_AVAILABLE:
                    for path in image_paths:
                        yield Image(path, classes="chat-image")

    def on_collapsible_toggled(self, event: Collapsible.Toggled) -> None:
        self._collapsed = event.collapsible.collapsed

    def refresh_task(self, task: Task) -> None:
        self.skill_task = task
        self.refresh(recompose=True)


class TasksContainer(Vertical):
    """Groups TaskWidgets for a single orchestration request."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._task_widgets: dict[str, TaskWidget] = {}

    def update_tasks(self, tasks: list[Task]) -> None:
        for task in tasks:
            if task.id in self._task_widgets:
                self._task_widgets[task.id].refresh_task(task)

    async def add_tasks(self, tasks: list[Task]) -> None:
        for task in tasks:
            if task.id not in self._task_widgets:
                widget = TaskWidget(task, classes=f"task-{task.status.value}")
                self._task_widgets[task.id] = widget
                await self.mount(widget)


class ThinkingWidget(Static):
    """Loading indicator with phase text."""

    def __init__(self, text: str = "Thinking...", **kwargs) -> None:
        super().__init__(**kwargs)
        self._text = text

    def compose(self) -> "ComposeResult":
        with Horizontal(classes="thinking-row"):
            yield LoadingIndicator(classes="thinking-spinner")
            yield Static(self._text, classes="thinking-text", id="thinking-label")

    def update_text(self, text: str) -> None:
        self._text = text
        try:
            label = self.query_one("#thinking-label", Static)
            label.update(text)
        except Exception:
            pass


class ChatHistory(VerticalScroll):
    """Scrollable container for chat messages and task progress."""

    can_focus = True

    DEFAULT_CSS = """
    ChatHistory {
        height: 100%;
        background: $surface;
        padding: 1 2;
    }

    ChatMessage {
        margin: 1 0;
        padding: 1 2;
        background: $panel;
    }

    ChatMessage.user {
        background: $primary 15%;
        border-left: thick $primary;
        margin-right: 4;
    }

    ChatMessage.assistant {
        background: $success 15%;
        border-left: thick $success;
        margin-left: 4;
    }

    ChatMessage Markdown {
        margin: 0;
        padding: 0;
    }

    .chat-image {
        width: auto;
        height: auto;
        max-height: 30;
        margin: 1 0;
    }

    ThinkingWidget {
        margin: 1 0 0 4;
        padding: 0 1;
        height: auto;
        background: $surface;
        border-left: thick $primary;
    }

    .thinking-row {
        height: auto;
        width: 100%;
    }

    .thinking-spinner {
        width: 2;
        height: 1;
        color: $primary;
    }

    .thinking-text {
        color: $text-muted;
        text-style: italic;
    }

    TasksContainer {
        margin: 0 0 0 4;
        padding: 0 1;
        height: auto;
        background: $surface;
        border-left: thick $warning;
    }

    TaskWidget {
        height: auto;
        padding: 0 1;
    }

    .task-row {
        height: auto;
        width: 100%;
    }

    .task-status {
        width: 2;
        color: $warning;
    }

    .task-completed .task-status {
        color: $success;
    }

    .task-failed .task-status {
        color: $error;
    }

    .task-desc {
        width: 1fr;
        color: $text;
    }

    .task-skills {
        width: auto;
        color: $text-muted;
        text-style: italic;
    }

    .task-result {
        margin: 0 0 0 2;
        padding: 0;
        height: auto;
    }

    .task-result Markdown {
        margin: 0;
        padding: 0 1;
    }
    """

    async def add_message(self, role: str, content: str = "") -> ChatMessage:
        message = ChatMessage(role, content, classes=role)
        await self.mount(message)
        self.scroll_end(animate=False)
        return message

    async def show_thinking(self, text: str = "Thinking...") -> None:
        await self.mount(ThinkingWidget(text, id="thinking"))
        self.scroll_end(animate=False)

    def update_thinking(self, text: str) -> None:
        try:
            self.query_one("#thinking", ThinkingWidget).update_text(text)
        except Exception:
            pass

    def hide_thinking(self) -> None:
        try:
            self.query_one("#thinking", ThinkingWidget).remove()
        except Exception:
            pass

    async def show_tasks(self, tasks: list[Task]) -> TasksContainer:
        container = TasksContainer()
        await self.mount(container)
        await container.add_tasks(tasks)
        self.scroll_end(animate=False)
        return container

    async def clear_messages(self) -> None:
        await self.remove_children()
