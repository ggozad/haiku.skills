# pragma: no cover
from typing import TYPE_CHECKING, Any

from rich.markup import escape
from textual.containers import Horizontal, VerticalScroll
from textual.css.query import NoMatches
from textual.widgets import LoadingIndicator, Markdown, Static

if TYPE_CHECKING:
    from textual.app import ComposeResult


_OP_COLORS = {
    "add": "green",
    "replace": "yellow",
    "remove": "red",
    "move": "cyan",
    "copy": "cyan",
}


def _summarize_delta(delta: list[dict[str, Any]]) -> str:
    """Summarize JSON patch operations into a compact Rich-markup description."""
    parts = []
    for op in delta:
        path = escape(op.get("path", "").replace("~1", "/").replace("~0", "~"))
        action = op.get("op", "?")
        color = _OP_COLORS.get(action, "white")
        parts.append(f"[{color}]{action}[/{color}] {path}")
    return "\n".join(parts) if parts else "state updated"


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


class ToolCallWidget(Static):
    """Displays a single tool call with status indicator."""

    def __init__(self, tool_call_id: str, tool_name: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.tool_call_id = tool_call_id
        self.tool_name = tool_name
        self._completed = False

    def compose(self) -> "ComposeResult":
        icon = "✓" if self._completed else "◌"
        with Horizontal(classes="task-row"):
            yield Static(icon, classes="task-status", id="tool-status")
            yield Static(self.tool_name, classes="task-desc", id="tool-desc")

    def update_description(self, text: str) -> None:
        try:
            desc = self.query_one("#tool-desc", Static)
            desc.update(text)
        except NoMatches:
            pass

    def mark_completed(self) -> None:
        self._completed = True
        try:
            status = self.query_one("#tool-status", Static)
            status.update("✓")
            self.add_class("task-completed")
        except NoMatches:
            pass


class StateDeltaWidget(Static):
    """Compact inline display of a state change."""

    def __init__(self, summary: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._summary = summary

    def compose(self) -> "ComposeResult":
        with Horizontal(classes="state-delta-row"):
            yield Static("↳", classes="state-delta-icon")
            yield Static(self._summary, classes="state-delta-text")


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
        except NoMatches:
            pass


class ChatHistory(VerticalScroll):
    """Scrollable container for chat messages, tool calls, and state."""

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

    ToolCallWidget {
        margin: 0 0 0 4;
        padding: 0 1;
        height: auto;
        background: $surface;
        border-left: thick $warning;
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

    .task-desc {
        width: 1fr;
        color: $text;
    }

    StateDeltaWidget {
        margin: 0 0 0 4;
        padding: 0 1;
        height: auto;
        background: $surface;
        border-left: thick $accent;
    }

    .state-delta-row {
        height: auto;
        width: 100%;
    }

    .state-delta-icon {
        width: 2;
        color: $accent;
    }

    .state-delta-text {
        width: 1fr;
        color: $text-muted;
        text-style: italic;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._tool_widgets: dict[str, ToolCallWidget] = {}

    async def add_message(self, role: str, content: str = "") -> ChatMessage:
        message = ChatMessage(role, content, classes=role)
        await self.mount(message)
        self.scroll_end(animate=False)
        return message

    async def show_thinking(self, text: str = "Thinking...") -> None:
        try:
            self.query_one("#thinking", ThinkingWidget).update_text(text)
        except NoMatches:
            await self.mount(ThinkingWidget(text, id="thinking"))
        self.scroll_end(animate=False)

    def hide_thinking(self) -> None:
        try:
            self.query_one("#thinking", ThinkingWidget).remove()
        except NoMatches:
            pass

    async def show_tool_call(self, tool_call_id: str, tool_name: str) -> None:
        widget = ToolCallWidget(tool_call_id, tool_name)
        self._tool_widgets[tool_call_id] = widget
        await self.mount(widget)
        self.scroll_end(animate=False)

    def update_tool_call(self, tool_call_id: str, completed: bool = False) -> None:
        widget = self._tool_widgets.get(tool_call_id)
        if widget and completed:
            widget.mark_completed()

    async def show_state_delta(self, delta: list[dict[str, Any]]) -> None:
        summary = _summarize_delta(delta)
        await self.mount(StateDeltaWidget(summary))
        self.scroll_end(animate=False)

    async def show_state_snapshot(self) -> None:
        await self.mount(StateDeltaWidget("state snapshot received"))
        self.scroll_end(animate=False)

    async def clear_messages(self) -> None:
        self._tool_widgets.clear()
        await self.remove_children()
