# pragma: no cover
import asyncio
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage
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
    import textual_image.widget  # noqa: F401
    from textual.app import App, SystemCommand
    from textual.binding import Binding
    from textual.widgets import Footer, Header, Input
    from textual.worker import Worker

    from haiku.skills.chat.widgets.chat_history import ChatHistory, TasksContainer

    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False
    App = object  # type: ignore


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
    ) -> None:
        super().__init__()
        self._model = model
        self._toolset = SkillToolset(
            skill_paths=skill_paths,
            skills=skills,
            use_entrypoints=use_entrypoints,
        )
        self._agent: Agent[None, str] | None = None
        self._history: list[ModelMessage] = []
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
        self.query_one(Input).focus()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        user_message = event.value.strip()
        if not user_message or self._is_processing:
            return

        event.input.clear()

        chat_history = self.query_one(ChatHistory)
        await chat_history.add_message("user", user_message)

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

        self._toolset.clear_tasks()
        poll_task = asyncio.create_task(self._poll_tasks())

        try:
            result = await self._agent.run(user_message, message_history=self._history)
            self._history = list(result.all_messages())
            poll_task.cancel()
            try:
                await poll_task
            except asyncio.CancelledError:
                pass

            chat_history.hide_thinking()
            await chat_history.add_message("assistant", result.output)
        except asyncio.CancelledError:
            poll_task.cancel()
            chat_history.hide_thinking()
            await chat_history.add_message("assistant", "*Cancelled*")
        except Exception as e:
            poll_task.cancel()
            chat_history.hide_thinking()
            await chat_history.add_message("assistant", f"Error: {e}")
        finally:
            self._is_processing = False
            self._current_worker = None
            chat_input = self.query_one(Input)
            chat_input.disabled = False
            chat_input.focus()

    async def _poll_tasks(self) -> None:
        chat_history = self.query_one(ChatHistory)
        tasks_container: TasksContainer | None = None

        while True:
            await asyncio.sleep(0.1)

            tasks = self._toolset.tasks
            if tasks and tasks_container is None:
                chat_history.hide_thinking()
                tasks_container = await chat_history.show_tasks(tasks)
                await chat_history.show_thinking("Executing tasks...")

            if tasks and tasks_container is not None:
                await tasks_container.add_tasks(tasks)
                tasks_container.update_tasks(tasks)

    def action_focus_input(self) -> None:
        if self._is_processing and self._current_worker:
            self._current_worker.cancel()
        self.query_one(Input).focus()

    async def action_clear_chat(self) -> None:
        self._history = []
        self._toolset.clear_tasks()
        chat_history = self.query_one(ChatHistory)
        await chat_history.clear_messages()
