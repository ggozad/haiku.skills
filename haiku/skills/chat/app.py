# pragma: no cover
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic_ai import Agent
from pydantic_ai.models import Model

from haiku.skills.agent import SkillToolset
from haiku.skills.models import Skill

try:
    import logfire

    logfire.configure(send_to_logfire="if-token-present", console=False)
    logfire.instrument_pydantic_ai()
except ImportError:
    pass

if TYPE_CHECKING:
    from textual.app import ComposeResult, SystemCommand

try:
    import json

    from ag_ui.core import (
        AssistantMessage,
        BaseEvent,
        EventType,
        RunAgentInput,
        StateDeltaEvent,
        TextMessageContentEvent,
        ToolCallEndEvent,
        ToolCallStartEvent,
        UserMessage,
    )
    from jsonpatch import JsonPatch
    from pydantic_ai.ag_ui import AGUIAdapter
    from rich.syntax import Syntax
    from textual.app import App, SystemCommand
    from textual.binding import Binding
    from textual.containers import VerticalScroll
    from textual.screen import ModalScreen
    from textual.widgets import Footer, Header, Input, Static
    from textual.worker import Worker

    from haiku.skills.chat.widgets.chat_history import ChatHistory

    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False
    App = object  # type: ignore


class StateScreen(ModalScreen[None]):
    """Modal screen showing the full AG-UI state as JSON."""

    CSS = """
    StateScreen {
        align: center middle;
        background: $background 60%;
    }

    #state-dialog {
        width: 80%;
        height: 80%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }

    #state-title {
        dock: top;
        text-style: bold;
        padding: 0 0 1 0;
        color: $primary;
    }

    #state-body {
        height: auto;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close", show=False),
    ]

    def __init__(self, state: dict[str, Any], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._state = state

    def compose(self) -> "ComposeResult":
        with VerticalScroll(id="state-dialog"):
            yield Static("State", id="state-title")
            text = (
                json.dumps(self._state, indent=2, default=str)
                if self._state
                else "(empty)"
            )
            yield Static(Syntax(text, "json", word_wrap=True), id="state-body")


class ChatApp(App):
    """Textual TUI for skill-powered agents."""

    TITLE = "haiku.skills Chat"

    CSS = """
    Screen {
        layout: grid;
        grid-size: 1 2;
        grid-rows: 1fr auto;
        background: $surface;
    }

    #chat-history {
        height: 100%;
    }

    Header {
        background: $primary;
    }

    Footer {
        background: $surface-darken-1;
    }
    """

    BINDINGS = [
        Binding("escape", "focus_input", "Focus Input", show=False),
    ]

    def __init__(
        self,
        model: Model,
        skill_paths: list[Path] | None = None,
        skills: list[Skill] | None = None,
        use_entrypoints: bool = False,
        skill_model: str | None = None,
    ) -> None:
        super().__init__()
        self._model = model
        self._toolset = SkillToolset(
            skill_paths=skill_paths,
            skills=skills,
            use_entrypoints=use_entrypoints,
            skill_model=skill_model,
        )
        self._agent: Agent[None, str] | None = None
        self._messages: list[Any] = []  # AG-UI Message objects
        self._state: dict[str, Any] = {}
        self._is_processing = False
        self._current_worker: Worker[None] | None = None

    def compose(self) -> "ComposeResult":
        yield Header()
        yield ChatHistory(id="chat-history")
        yield Input(placeholder="Ask a question...", id="chat-input")
        yield Footer()

    def get_system_commands(self, screen: Any) -> Iterable["SystemCommand"]:
        yield from super().get_system_commands(screen)
        yield SystemCommand(
            "View state",
            "Show the current AG-UI state",
            self.action_view_state,
        )
        yield SystemCommand(
            "Clear chat",
            "Clear the chat history",
            self.action_clear_chat,
        )

    async def on_mount(self) -> None:
        self._agent = Agent(
            self._model,
            instructions=self._toolset.system_prompt,
            toolsets=[self._toolset],
        )
        self._state = self._toolset.build_state_snapshot()
        self.query_one(Input).focus()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        user_message = event.value.strip()
        if not user_message or self._is_processing:
            return

        event.input.clear()

        chat_history = self.query_one(ChatHistory)
        await chat_history.add_message("user", user_message)

        self._messages.append(
            UserMessage(
                id=str(uuid.uuid4()),
                role="user",
                content=user_message,
            )
        )

        self._is_processing = True
        self.query_one(Input).disabled = True
        self._current_worker = self.run_worker(
            self._run_agent(user_message), exclusive=True
        )

    async def _run_agent(self, user_message: str) -> None:
        if not self._agent:
            return

        chat_history = self.query_one(ChatHistory)
        await chat_history.show_thinking()

        run_input = RunAgentInput(
            thread_id="tui",
            run_id=str(uuid.uuid4()),
            messages=self._messages,
            state=self._state,
            tools=[],
            context=[],
            forwarded_props={},
        )

        adapter = AGUIAdapter(
            agent=self._agent,
            run_input=run_input,
        )

        message = None
        accumulated_text = ""

        try:
            async for event in adapter.run_stream():
                if not isinstance(event, BaseEvent):
                    continue
                if event.type == EventType.TEXT_MESSAGE_START:
                    chat_history.hide_thinking()
                    message = await chat_history.add_message("assistant")
                    accumulated_text = ""
                elif event.type == EventType.TEXT_MESSAGE_CONTENT:
                    assert isinstance(event, TextMessageContentEvent)
                    accumulated_text += event.delta
                    if message:
                        message.update_content(accumulated_text)
                        chat_history.scroll_end(animate=False)
                elif event.type == EventType.TEXT_MESSAGE_END:
                    self._messages.append(
                        AssistantMessage(
                            id=str(uuid.uuid4()),
                            role="assistant",
                            content=accumulated_text,
                        )
                    )
                elif event.type == EventType.TOOL_CALL_START:
                    assert isinstance(event, ToolCallStartEvent)
                    chat_history.hide_thinking()
                    await chat_history.show_tool_call(
                        event.tool_call_id, event.tool_call_name
                    )
                    await chat_history.show_thinking("Executing tasks...")
                elif event.type == EventType.TOOL_CALL_END:
                    assert isinstance(event, ToolCallEndEvent)
                    chat_history.update_tool_call(event.tool_call_id, completed=True)
                elif event.type == EventType.STATE_DELTA:
                    assert isinstance(event, StateDeltaEvent)
                    patch = JsonPatch(event.delta)
                    self._state = patch.apply(self._state)
                    self._toolset.restore_state_snapshot(self._state)
                    await chat_history.show_state_delta(event.delta)
                elif event.type == EventType.STATE_SNAPSHOT:
                    self._state = getattr(event, "snapshot", self._state)
                    self._toolset.restore_state_snapshot(self._state)
                    await chat_history.show_state_snapshot()
                elif event.type == EventType.RUN_FINISHED:
                    chat_history.hide_thinking()
                elif event.type == EventType.RUN_ERROR:
                    chat_history.hide_thinking()
                    error_msg = getattr(event, "message", "Unknown error")
                    await chat_history.add_message("assistant", f"Error: {error_msg}")
                elif event.type == EventType.THINKING_START:
                    await chat_history.show_thinking()
                elif event.type == EventType.THINKING_END:
                    chat_history.hide_thinking()

        except Exception as e:
            chat_history.hide_thinking()
            await chat_history.add_message("assistant", f"Error: {e}")
        finally:
            self._is_processing = False
            self._current_worker = None
            chat_input = self.query_one(Input)
            chat_input.disabled = False
            chat_input.focus()

    def action_view_state(self) -> None:
        self.push_screen(StateScreen(self._state))

    def action_focus_input(self) -> None:
        if self._is_processing and self._current_worker:
            self._current_worker.cancel()
        self.query_one(Input).focus()

    async def action_clear_chat(self) -> None:
        self._messages = []
        self._state = {}
        chat_history = self.query_one(ChatHistory)
        await chat_history.clear_messages()
