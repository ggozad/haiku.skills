from pathlib import Path
from unittest.mock import MagicMock

import pytest

from haiku.skills.discovery import (
    discover_from_entrypoints,
    discover_from_paths,
    discover_resources,
)
from haiku.skills.models import Skill, SkillMetadata, SkillSource

FIXTURES = Path(__file__).parent / "fixtures"


class TestDiscoverFromPaths:
    def test_discovers_skills_in_directory(self):
        skills = discover_from_paths([FIXTURES])
        names = {s.metadata.name for s in skills}
        assert "simple-skill" in names
        assert "skill-with-refs" in names

    def test_returns_filesystem_source(self):
        skills = discover_from_paths([FIXTURES])
        for skill in skills:
            assert skill.source == SkillSource.FILESYSTEM

    def test_sets_path_to_skill_directory(self):
        skills = discover_from_paths([FIXTURES])
        by_name = {s.metadata.name: s for s in skills}
        assert by_name["simple-skill"].path == FIXTURES / "simple-skill"

    def test_instructions_not_loaded(self):
        skills = discover_from_paths([FIXTURES])
        for skill in skills:
            assert skill.instructions is None

    def test_name_must_match_directory(self, tmp_path: Path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: wrong-name\ndescription: Mismatch.\n---\nBody.\n"
        )
        with pytest.raises(ValueError, match="does not match"):
            discover_from_paths([tmp_path])

    def test_skips_non_skill_entries(self, tmp_path: Path):
        # A file (not a directory) should be skipped
        (tmp_path / "readme.txt").write_text("not a skill")
        # A directory without SKILL.md should be skipped
        (tmp_path / "not-a-skill").mkdir()
        skills = discover_from_paths([tmp_path])
        assert skills == []

    def test_nonexistent_path_raises(self):
        with pytest.raises(FileNotFoundError):
            discover_from_paths([Path("/nonexistent/path")])

    def test_multiple_paths(self, tmp_path: Path):
        dir_a = tmp_path / "a"
        dir_a.mkdir()
        skill_a = dir_a / "skill-a"
        skill_a.mkdir()
        (skill_a / "SKILL.md").write_text(
            "---\nname: skill-a\ndescription: Skill A.\n---\nBody A.\n"
        )

        dir_b = tmp_path / "b"
        dir_b.mkdir()
        skill_b = dir_b / "skill-b"
        skill_b.mkdir()
        (skill_b / "SKILL.md").write_text(
            "---\nname: skill-b\ndescription: Skill B.\n---\nBody B.\n"
        )

        skills = discover_from_paths([dir_a, dir_b])
        names = {s.metadata.name for s in skills}
        assert names == {"skill-a", "skill-b"}


class TestDiscoverResources:
    def test_finds_files_in_references_and_assets(self):
        resources = discover_resources(FIXTURES / "skill-with-refs")
        assert "assets/template.txt" in resources
        assert "references/REFERENCE.md" in resources

    def test_excludes_skill_md(self):
        resources = discover_resources(FIXTURES / "skill-with-refs")
        assert "SKILL.md" not in resources

    def test_excludes_scripts_directory(self):
        resources = discover_resources(FIXTURES / "simple-skill")
        assert resources == []

    def test_sorted_output(self):
        resources = discover_resources(FIXTURES / "skill-with-refs")
        assert resources == sorted(resources)

    def test_empty_for_skill_with_only_skill_md_and_scripts(self):
        resources = discover_resources(FIXTURES / "simple-skill")
        assert resources == []

    def test_handles_nested_subdirectories(self, tmp_path: Path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: Test.\n---\nBody.\n"
        )
        nested = skill_dir / "refs" / "deep"
        nested.mkdir(parents=True)
        (nested / "doc.txt").write_text("nested doc")
        resources = discover_resources(skill_dir)
        assert resources == ["refs/deep/doc.txt"]


class TestDiscoverFromEntrypoints:
    def test_loads_from_entrypoints(self, monkeypatch: pytest.MonkeyPatch):
        skill = Skill(
            metadata=SkillMetadata(name="ep-skill", description="From entrypoint."),
            source=SkillSource.ENTRYPOINT,
        )
        mock_ep = MagicMock()
        mock_ep.load.return_value = lambda: skill

        monkeypatch.setattr(
            "haiku.skills.discovery.entry_points",
            lambda group: [mock_ep],
        )
        skills = discover_from_entrypoints()
        assert len(skills) == 1
        assert skills[0].metadata.name == "ep-skill"
        assert skills[0].source == SkillSource.ENTRYPOINT

    def test_empty_entrypoints(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            "haiku.skills.discovery.entry_points",
            lambda group: [],
        )
        skills = discover_from_entrypoints()
        assert skills == []
