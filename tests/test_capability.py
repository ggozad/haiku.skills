from pathlib import Path

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.result import RunUsage

from haiku.skills.capability import SkillsCapability
from haiku.skills.models import Skill, SkillMetadata, SkillSource
from haiku.skills.prompts import DEFAULT_PREAMBLE, build_system_prompt

FIXTURES = Path(__file__).parent / "fixtures"


def _make_ctx() -> RunContext[None]:
    return RunContext(
        deps=None, model=TestModel(), usage=RunUsage(), prompt="test", run_step=0
    )


class TestSkillsCapability:
    def test_provides_toolset(self):
        cap = SkillsCapability(skill_paths=[FIXTURES])
        toolset = cap.get_toolset()
        assert toolset is cap.toolset
        assert "simple-skill" in toolset.registry.names

    def test_provides_instructions_subagent_mode(self):
        cap = SkillsCapability(skill_paths=[FIXTURES])
        instructions_fn = cap.get_instructions()
        assert callable(instructions_fn)
        result = instructions_fn(_make_ctx())
        expected = build_system_prompt(cap.toolset.skill_catalog, use_subagents=True)
        assert result == expected

    def test_provides_instructions_direct_mode(self):
        cap = SkillsCapability(skill_paths=[FIXTURES], use_subagents=False)
        instructions_fn = cap.get_instructions()
        result = instructions_fn(_make_ctx())
        expected = build_system_prompt(cap.toolset.skill_catalog, use_subagents=False)
        assert result == expected

    def test_custom_preamble(self):
        preamble = "You are a test agent."
        cap = SkillsCapability(skill_paths=[FIXTURES], preamble=preamble)
        instructions_fn = cap.get_instructions()
        result = instructions_fn(_make_ctx())
        assert preamble in result
        assert DEFAULT_PREAMBLE not in result

    def test_with_skill_objects(self):
        skill = Skill(
            metadata=SkillMetadata(name="test-skill", description="A test."),
            source=SkillSource.ENTRYPOINT,
        )
        cap = SkillsCapability(skills=[skill])
        assert "test-skill" in cap.toolset.registry.names

    def test_skill_model_forwarded(self):
        cap = SkillsCapability(skill_paths=[FIXTURES], skill_model="openai:gpt-4o")
        assert cap.toolset._skill_model == "openai:gpt-4o"

    async def test_integration_with_agent(self):
        skill = Skill(
            metadata=SkillMetadata(name="greeter", description="Greets people."),
            source=SkillSource.ENTRYPOINT,
            instructions="Greet the user.",
        )
        cap = SkillsCapability(skills=[skill])
        agent = Agent(TestModel(), capabilities=[cap])
        result = await agent.run("Hello")
        assert result.output
