from pathlib import Path

import pytest

from haiku.skills.models import Skill, SkillMetadata, SkillSource, SkillValidationError
from haiku.skills.registry import SkillRegistry
from haiku.skills.signing import TrustedIdentity

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

    def test_discover_from_paths(self):
        registry = SkillRegistry()
        errors = registry.discover(paths=[FIXTURES])
        assert "simple-skill" in registry.names
        assert "skill-with-refs" in registry.names
        assert errors == []

    def test_discover_loads_instructions(self):
        registry = SkillRegistry()
        errors = registry.discover(paths=[FIXTURES])
        skill = registry.get("simple-skill")
        assert skill is not None
        assert skill.instructions is not None
        assert "# Simple Skill" in skill.instructions
        assert errors == []

    def test_discover_loads_script_tools(self):
        registry = SkillRegistry()
        errors = registry.discover(paths=[FIXTURES])
        skill = registry.get("simple-skill")
        assert skill is not None
        assert len(skill.tools) == 1
        tool = skill.tools[0]
        assert hasattr(tool, "name") and tool.name == "greet"
        assert errors == []

    def test_discover_loads_resources(self):
        registry = SkillRegistry()
        errors = registry.discover(paths=[FIXTURES])
        skill = registry.get("skill-with-refs")
        assert skill is not None
        assert "references/REFERENCE.md" in skill.resources
        assert "assets/template.txt" in skill.resources
        assert errors == []

    def test_discover_from_entrypoints(self, monkeypatch: pytest.MonkeyPatch):
        skill = _make_skill("ep-skill", source=SkillSource.ENTRYPOINT)
        mock_ep = type("MockEP", (), {"load": lambda self: lambda: skill})()
        monkeypatch.setattr(
            "haiku.skills.discovery.entry_points",
            lambda group: [mock_ep],
        )
        registry = SkillRegistry()
        errors = registry.discover(use_entrypoints=True)
        assert "ep-skill" in registry.names
        assert errors == []

    def test_entrypoint_skips_already_registered(self, monkeypatch: pytest.MonkeyPatch):
        ep_skill = _make_skill("overlap", source=SkillSource.ENTRYPOINT)
        mock_ep = type("MockEP", (), {"load": lambda self: lambda: ep_skill})()
        monkeypatch.setattr(
            "haiku.skills.discovery.entry_points",
            lambda group: [mock_ep],
        )
        manual_skill = _make_skill(
            "overlap", description="Manual version.", source=SkillSource.FILESYSTEM
        )
        registry = SkillRegistry()
        registry.register(manual_skill)
        errors = registry.discover(use_entrypoints=True)
        assert registry.get("overlap") is manual_skill
        assert errors == []

    def test_discover_returns_errors(self, tmp_path: Path):
        valid = tmp_path / "good-skill"
        valid.mkdir()
        (valid / "SKILL.md").write_text(
            "---\nname: good-skill\ndescription: Good.\n---\nBody.\n"
        )
        broken = tmp_path / "broken-skill"
        broken.mkdir()
        (broken / "SKILL.md").write_text(
            "---\nname: wrong-name\ndescription: Broken.\n---\nBody.\n"
        )
        registry = SkillRegistry()
        errors = registry.discover(paths=[tmp_path])
        assert "good-skill" in registry.names
        assert len(errors) == 1
        assert isinstance(errors[0], SkillValidationError)
        assert errors[0].path == broken

    def test_discover_passes_trusted_identities(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: Test.\n---\nBody.\n"
        )
        (skill_dir / "SKILL.sigstore").write_text('{"bundle": "data"}')

        monkeypatch.setattr(
            "haiku.skills.discovery.verify_skill", lambda *a, **kw: True
        )

        identities = [TrustedIdentity(identity="a@b.com", issuer="https://issuer")]
        registry = SkillRegistry()
        errors = registry.discover(paths=[skill_dir], trusted_identities=identities)
        assert errors == []
        skill = registry.get("my-skill")
        assert skill is not None
        assert skill.verified is True
