# pragma: no cover
from typing import TYPE_CHECKING

from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import LoadingIndicator, Markdown, Static

from haiku.skills.models import Task, TaskStatus

if TYPE_CHECKING:
    from textual.app import ComposeResult


class ChatMessage(Static):
    """A single chat message with role styling."""

    def __init__(self, role: str, content: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self.role = role
        self.content = content

    def compose(self) -> "ComposeResult":
        prefix = "**You:**" if self.role == "user" else "**Assistant:**"
        yield Markdown(f"{prefix}\n\n{self.content}", id="message-content")

    def update_content(self, content: str) -> None:
        self.content = content
        prefix = "**You:**" if self.role == "user" else "**Assistant:**"
        markdown = self.query_one("#message-content", Markdown)
        markdown.update(f"{prefix}\n\n{content}")


class TaskWidget(Static):
    """Displays a single orchestrator task with status indicator."""

    STATUS_ICONS = {
        TaskStatus.PENDING: "○",
        TaskStatus.IN_PROGRESS: "◌",
        TaskStatus.COMPLETED: "✓",
        TaskStatus.FAILED: "✗",
    }

    def __init__(self, task: Task, **kwargs) -> None:
        super().__init__(**kwargs)
        self.skill_task = task

    def compose(self) -> "ComposeResult":
        icon = self.STATUS_ICONS.get(self.skill_task.status, "?")
        skills = ", ".join(self.skill_task.skills)
        with Horizontal(classes="task-row"):
            yield Static(icon, classes="task-status")
            yield Static(self.skill_task.description, classes="task-desc")
            yield Static(f"[{skills}]", classes="task-skills")

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
