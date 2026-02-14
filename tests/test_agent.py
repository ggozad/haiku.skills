from pathlib import Path

import pytest
from pydantic_ai.models.test import TestModel
from pydantic_ai.toolsets.function import FunctionToolset

from haiku.skills.agent import SkillAgent, _last_tool_result, create_agent
from haiku.skills.models import (
    AgentState,
    Skill,
    SkillMetadata,
    SkillSource,
    TaskStatus,
)
from haiku.skills.prompts import SKILL_PROMPT
from haiku.skills.registry import SkillRegistry

FIXTURES = Path(__file__).parent / "fixtures"


class TestCreateAgent:
    async def test_create_with_paths(self, allow_model_requests: None):
        agent = create_agent(model=TestModel(), skill_paths=[FIXTURES])
        assert "simple-skill" in agent.skills
        assert "skill-with-refs" in agent.skills

    async def test_create_with_skill_objects(self, allow_model_requests: None):
        skill = Skill(
            metadata=SkillMetadata(name="custom", description="Custom skill."),
            source=SkillSource.ENTRYPOINT,
            instructions="Do custom things.",
        )
        agent = create_agent(model=TestModel(), skills=[skill])
        assert "custom" in agent.skills

    async def test_create_with_entrypoints(
        self, monkeypatch: pytest.MonkeyPatch, allow_model_requests: None
    ):
        skill = Skill(
            metadata=SkillMetadata(name="ep-skill", description="From entrypoint."),
            source=SkillSource.ENTRYPOINT,
        )
        mock_ep = type("MockEP", (), {"load": lambda self: lambda: skill})()
        monkeypatch.setattr(
            "haiku.skills.discovery.entry_points",
            lambda group: [mock_ep],
        )
        agent = create_agent(model=TestModel(), use_entrypoints=True)
        assert "ep-skill" in agent.skills

    async def test_create_with_paths_and_skills(self, allow_model_requests: None):
        skill = Skill(
            metadata=SkillMetadata(name="extra", description="Extra skill."),
            source=SkillSource.ENTRYPOINT,
        )
        agent = create_agent(model=TestModel(), skill_paths=[FIXTURES], skills=[skill])
        assert "simple-skill" in agent.skills
        assert "extra" in agent.skills


class TestRunSkill:
    async def test_run_skill(self, allow_model_requests: None):
        agent = create_agent(model=TestModel(), skill_paths=[FIXTURES])
        result = await agent._run_skill("simple-skill", "Do something.")
        assert result

    async def test_run_skill_activates_skill(self, allow_model_requests: None):
        agent = create_agent(model=TestModel(), skill_paths=[FIXTURES])
        await agent._run_skill("simple-skill", "Do something.")
        skill = agent.registry.get("simple-skill")
        assert skill is not None
        assert skill.instructions is not None

    async def test_run_skill_unknown_skill_fails(self, allow_model_requests: None):
        agent = create_agent(model=TestModel(), skill_paths=[FIXTURES])
        with pytest.raises(KeyError, match="nonexistent-skill"):
            await agent._run_skill("nonexistent-skill", "Do something.")

    async def test_run_skill_with_tools(self, allow_model_requests: None):
        def greet(name: str) -> str:
            """Greet someone by name."""
            return f"Hello, {name}!"

        meta = SkillMetadata(name="greeter", description="Greets people.")
        skill = Skill(
            metadata=meta,
            source=SkillSource.FILESYSTEM,
            instructions="Use the greet tool.",
            tools=[greet],
        )
        registry = SkillRegistry()
        registry.register(skill)
        agent = SkillAgent(model=TestModel(), registry=registry)
        result = await agent._run_skill("greeter", "Greet Alice.")
        assert result

    async def test_run_skill_with_toolsets(self, allow_model_requests: None):
        def greet(name: str) -> str:
            """Greet someone by name."""
            return f"Hello, {name}!"

        toolset = FunctionToolset()
        toolset.add_function(greet)
        meta = SkillMetadata(name="greeter", description="Greets people.")
        skill = Skill(
            metadata=meta,
            source=SkillSource.FILESYSTEM,
            instructions="Use the greet toolset.",
            toolsets=[toolset],
        )
        registry = SkillRegistry()
        registry.register(skill)
        agent = SkillAgent(model=TestModel(), registry=registry)
        result = await agent._run_skill("greeter", "Greet Alice.")
        assert result


class TestLastToolResult:
    def test_returns_none_for_empty_messages(self):
        assert _last_tool_result([]) is None

    def test_returns_none_when_no_tool_returns(self):
        from pydantic_ai.messages import ModelRequest, UserPromptPart

        messages = [ModelRequest(parts=[UserPromptPart(content="hello")])]
        assert _last_tool_result(messages) is None


class TestPrompts:
    def test_skill_prompt_has_placeholders(self):
        assert "{task_description}" in SKILL_PROMPT
        assert "{skill_instructions}" in SKILL_PROMPT


class TestSkillAgent:
    async def test_registry_property(self, allow_model_requests: None):
        agent = create_agent(model=TestModel(), skill_paths=[FIXTURES])
        assert agent.registry is not None
        assert len(agent.registry.names) >= 2

    async def test_skills_property(self, allow_model_requests: None):
        agent = create_agent(model=TestModel(), skill_paths=[FIXTURES])
        assert isinstance(agent.skills, list)
        assert all(isinstance(s, str) for s in agent.skills)

    async def test_direct_chat(self, allow_model_requests: None):
        """Agent responds directly without skill execution for simple chat."""
        model = TestModel(call_tools=[], custom_output_text="Hello there!")
        agent = create_agent(model=model, skill_paths=[FIXTURES])
        state = AgentState()
        answer = await agent.run("Hello", state)
        assert answer == "Hello there!"
        assert state.tasks == []

    async def test_run_with_skill_execution(self, allow_model_requests: None):
        """Agent delegates to skills and tracks tasks in state."""
        skill = Skill(
            metadata=SkillMetadata(name="a", description="Test skill."),
            source=SkillSource.ENTRYPOINT,
            instructions="Do things.",
        )
        agent = create_agent(model=TestModel(), skills=[skill])
        state = AgentState()
        answer = await agent.run("Do something.", state)
        assert answer
        assert len(state.tasks) >= 1
        for task in state.tasks:
            assert task.status == TaskStatus.COMPLETED

    async def test_run_with_unknown_skill_records_failure(
        self, allow_model_requests: None
    ):
        """Unknown skill in execute_skill records task failure."""
        agent = create_agent(model=TestModel(), skill_paths=[FIXTURES])
        state = AgentState()
        await agent.run("Do something.", state)
        assert len(state.tasks) >= 1
        for task in state.tasks:
            assert task.status == TaskStatus.FAILED
            assert task.error is not None

    async def test_run_optional_state(self, allow_model_requests: None):
        """run() works without state arg."""
        model = TestModel(call_tools=[], custom_output_text="Hi!")
        agent = create_agent(model=model, skill_paths=[FIXTURES])
        answer = await agent.run("Hello")
        assert answer == "Hi!"

    async def test_history_maintained(self, allow_model_requests: None):
        """Conversation history persists across runs."""
        model = TestModel(call_tools=[], custom_output_text="Response")
        agent = create_agent(model=model, skill_paths=[FIXTURES])
        await agent.run("First message")
        assert len(agent.history) > 0
        history_after_first = len(agent.history)
        await agent.run("Second message")
        assert len(agent.history) > history_after_first

    async def test_clear_history(self, allow_model_requests: None):
        """History can be cleared."""
        model = TestModel(call_tools=[], custom_output_text="Hi")
        agent = create_agent(model=model, skill_paths=[FIXTURES])
        await agent.run("Hello")
        assert len(agent.history) > 0
        agent.clear_history()
        assert len(agent.history) == 0
