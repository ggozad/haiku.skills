from pathlib import Path

import pytest
from pydantic_ai.models.test import TestModel

from haiku.skills.agent import create_agent
from haiku.skills.models import (
    OrchestratorPhase,
    OrchestratorState,
    Skill,
    SkillMetadata,
    SkillSource,
    TaskStatus,
)

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


class TestSkillAgent:
    async def test_registry_property(self, allow_model_requests: None):
        agent = create_agent(model=TestModel(), skill_paths=[FIXTURES])
        assert agent.registry is not None
        assert len(agent.registry.names) >= 2

    async def test_skills_property(self, allow_model_requests: None):
        agent = create_agent(model=TestModel(), skill_paths=[FIXTURES])
        assert isinstance(agent.skills, list)
        assert all(isinstance(s, str) for s in agent.skills)

    async def test_run(self, allow_model_requests: None):
        agent = create_agent(model=TestModel(), skill_paths=[FIXTURES])
        state = OrchestratorState()
        result = await agent.run("Do something with simple-skill.", state)
        assert result.answer
        assert len(result.tasks) >= 1
        for task in result.tasks:
            assert task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)

    async def test_run_updates_state(self, allow_model_requests: None):
        agent = create_agent(model=TestModel(), skill_paths=[FIXTURES])
        state = OrchestratorState()
        result = await agent.run("Do something.", state)
        assert state.phase == OrchestratorPhase.IDLE
        assert state.plan is not None
        assert state.tasks == result.tasks
