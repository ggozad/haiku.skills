from pathlib import Path

import pytest

from haiku.skills.models import Skill, SkillMetadata, SkillSource
from haiku.skills.registry import SkillRegistry

FIXTURES = Path(__file__).parent / "fixtures"


def _make_skill(
    name: str = "test-skill",
    description: str = "A test skill.",
    source: SkillSource = SkillSource.FILESYSTEM,
    path: Path | None = None,
    instructions: str | None = None,
) -> Skill:
    return Skill(
        metadata=SkillMetadata(name=name, description=description),
        source=source,
        path=path,
        instructions=instructions,
    )


class TestSkillRegistry:
    def test_register_and_get(self):
        registry = SkillRegistry()
        skill = _make_skill()
        registry.register(skill)
        assert registry.get("test-skill") is skill

    def test_get_unknown_returns_none(self):
        registry = SkillRegistry()
        assert registry.get("unknown") is None

    def test_names(self):
        registry = SkillRegistry()
        registry.register(_make_skill("alpha"))
        registry.register(_make_skill("beta"))
        assert registry.names == ["alpha", "beta"]

    def test_list_metadata(self):
        registry = SkillRegistry()
        registry.register(_make_skill("alpha", "Skill A."))
        registry.register(_make_skill("beta", "Skill B."))
        metadata_list = registry.list_metadata()
        assert len(metadata_list) == 2
        names = {m.name for m in metadata_list}
        assert names == {"alpha", "beta"}

    def test_duplicate_name_raises(self):
        registry = SkillRegistry()
        registry.register(_make_skill("dup"))
        with pytest.raises(ValueError, match="already registered"):
            registry.register(_make_skill("dup"))

    def test_activate_loads_instructions(self):
        registry = SkillRegistry()
        skill = _make_skill(
            "simple-skill",
            "A simple test skill that does basic operations.",
            path=FIXTURES / "simple-skill",
        )
        registry.register(skill)
        assert skill.instructions is None

        registry.activate("simple-skill")
        assert skill.instructions is not None
        assert "# Simple Skill" in skill.instructions

    def test_activate_discovers_script_tools(self):
        registry = SkillRegistry()
        skill = _make_skill(
            "simple-skill",
            "A simple test skill that does basic operations.",
            path=FIXTURES / "simple-skill",
        )
        registry.register(skill)
        registry.activate("simple-skill")
        assert len(skill.tools) == 1
        tool = skill.tools[0]
        assert hasattr(tool, "name") and tool.name == "greet"

    def test_activate_unknown_raises(self):
        registry = SkillRegistry()
        with pytest.raises(KeyError, match="unknown"):
            registry.activate("unknown")

    def test_activate_already_loaded_is_noop(self):
        registry = SkillRegistry()
        skill = _make_skill(instructions="Already loaded.")
        registry.register(skill)
        registry.activate("test-skill")
        assert skill.instructions == "Already loaded."

    def test_activate_without_path_is_noop(self):
        registry = SkillRegistry()
        skill = _make_skill()
        registry.register(skill)
        registry.activate("test-skill")
        assert skill.instructions is None

    def test_discover_from_paths(self):
        registry = SkillRegistry()
        registry.discover(paths=[FIXTURES])
        assert "simple-skill" in registry.names
        assert "skill-with-refs" in registry.names

    def test_discover_from_entrypoints(self, monkeypatch: pytest.MonkeyPatch):
        skill = _make_skill("ep-skill", source=SkillSource.ENTRYPOINT)
        mock_ep = type("MockEP", (), {"load": lambda self: lambda: skill})()
        monkeypatch.setattr(
            "haiku.skills.discovery.entry_points",
            lambda group: [mock_ep],
        )
        registry = SkillRegistry()
        registry.discover(use_entrypoints=True)
        assert "ep-skill" in registry.names
