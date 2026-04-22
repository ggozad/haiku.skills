from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import pytest
from ag_ui.core import BaseEvent
from pydantic import BaseModel
from pydantic_ai import RunContext
from pydantic_ai.models.test import TestModel

from haiku.skills.agent import _run_skill
from haiku.skills.models import Skill, SkillMetadata, SkillSource
from haiku.skills.state import SkillRunDeps, SkillRunDepsProtocol


@dataclass
class DepsWithDB:
    state: BaseModel | None = None
    emit: Callable[[BaseEvent], None] = field(default=lambda _: None)
    db: Any = None
    calls: int = 0


class TestLifespan:
    async def test_hook_fires_once_across_tool_calls(
        self, allow_model_requests: None
    ) -> None:
        events: list[str] = []
        observed: list[Any] = []

        @asynccontextmanager
        async def lifespan(deps: DepsWithDB):
            events.append("enter")
            deps.db = "connected"
            try:
                yield
            finally:
                events.append("exit")
                deps.db = "closed"

        def ping_a(ctx: RunContext[DepsWithDB]) -> str:
            """Ping a."""
            ctx.deps.calls += 1
            observed.append(ctx.deps.db)
            return "a"

        def ping_b(ctx: RunContext[DepsWithDB]) -> str:
            """Ping b."""
            ctx.deps.calls += 1
            observed.append(ctx.deps.db)
            return "b"

        def ping_c(ctx: RunContext[DepsWithDB]) -> str:
            """Ping c."""
            ctx.deps.calls += 1
            observed.append(ctx.deps.db)
            return "c"

        skill = Skill(
            metadata=SkillMetadata(name="pinger", description="Pings."),
            source=SkillSource.ENTRYPOINT,
            instructions="Ping.",
            tools=[ping_a, ping_b, ping_c],
            deps_type=DepsWithDB,
            lifespan=lifespan,
        )

        result, *_ = await _run_skill(TestModel(), skill, "Ping all three.")

        assert result
        assert events == ["enter", "exit"]
        assert observed == ["connected", "connected", "connected"]

    async def test_exception_propagates_through_cm(
        self, allow_model_requests: None
    ) -> None:
        exit_info: dict[str, Any] = {}

        class Lifespan:
            async def __aenter__(self) -> None:
                return None

            async def __aexit__(
                self,
                exc_type: type[BaseException] | None,
                exc: BaseException | None,
                tb: Any,
            ) -> None:
                exit_info["exc_type"] = exc_type
                exit_info["exc"] = exc

        def factory(deps: SkillRunDepsProtocol) -> Lifespan:
            return Lifespan()

        def boom(ctx: RunContext[SkillRunDeps]) -> str:
            """Raise on call."""
            raise RuntimeError("boom")

        skill = Skill(
            metadata=SkillMetadata(name="boomer", description="Raises."),
            source=SkillSource.ENTRYPOINT,
            instructions="Call boom.",
            tools=[boom],
            lifespan=factory,
        )

        with pytest.raises(Exception):
            await _run_skill(TestModel(), skill, "Boom.")

        assert exit_info["exc_type"] is not None
        assert exit_info["exc"] is not None

    async def test_no_lifespan_is_noop(self, allow_model_requests: None) -> None:
        def noop() -> str:
            """No-op."""
            return "ok"

        skill = Skill(
            metadata=SkillMetadata(name="noop", description="Noop."),
            source=SkillSource.ENTRYPOINT,
            instructions="Call noop.",
            tools=[noop],
        )

        assert skill.lifespan is None
        result, *_ = await _run_skill(TestModel(), skill, "Do it.")
        assert result

    async def test_per_invocation_isolation(self, allow_model_requests: None) -> None:
        enters: list[int] = []
        observed: list[int] = []

        @asynccontextmanager
        async def lifespan(deps: DepsWithDB):
            deps.calls = 0
            enters.append(id(deps))
            yield

        def ping(ctx: RunContext[DepsWithDB]) -> str:
            """Ping."""
            ctx.deps.calls += 1
            observed.append(ctx.deps.calls)
            return "pong"

        skill = Skill(
            metadata=SkillMetadata(name="pinger", description="Pings."),
            source=SkillSource.ENTRYPOINT,
            instructions="Ping once.",
            tools=[ping],
            deps_type=DepsWithDB,
            lifespan=lifespan,
        )

        await _run_skill(TestModel(), skill, "Ping.")
        await _run_skill(TestModel(), skill, "Ping again.")

        assert len(enters) == 2
        assert enters[0] != enters[1]
        assert observed == [1, 1]

    async def test_lifespan_without_custom_deps(
        self, allow_model_requests: None
    ) -> None:
        """Lifespan can do useful work without requiring a custom deps class."""
        events: list[str] = []

        @asynccontextmanager
        async def lifespan(deps: SkillRunDeps):
            events.append("enter")
            try:
                yield
            finally:
                events.append("exit")

        def noop() -> str:
            """No-op."""
            return "ok"

        skill = Skill(
            metadata=SkillMetadata(name="noop", description="Noop."),
            source=SkillSource.ENTRYPOINT,
            instructions="Call noop.",
            tools=[noop],
            lifespan=lifespan,
        )

        await _run_skill(TestModel(), skill, "Do it.")
        assert events == ["enter", "exit"]

    async def test_reconfigure_preserves_lifespan(self) -> None:
        @asynccontextmanager
        async def lifespan(deps: SkillRunDepsProtocol):
            yield

        def make_skill(**_: Any) -> Skill:
            return Skill(
                metadata=SkillMetadata(name="s", description="s."),
                source=SkillSource.ENTRYPOINT,
                instructions="x",
                lifespan=lifespan,
            )

        skill = make_skill()
        skill._factory = make_skill
        assert skill.lifespan is lifespan

        skill.reconfigure()
        assert skill.lifespan is lifespan


class TestLifespanProperty:
    def test_lifespan_setter(self) -> None:
        @asynccontextmanager
        async def lifespan(deps: SkillRunDepsProtocol):
            yield

        skill = Skill(
            metadata=SkillMetadata(name="s", description="s."),
            source=SkillSource.ENTRYPOINT,
        )
        assert skill.lifespan is None
        skill.lifespan = lifespan
        assert skill.lifespan is lifespan
        skill.lifespan = None
        assert skill.lifespan is None
