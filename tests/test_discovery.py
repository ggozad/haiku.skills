from pathlib import Path
from unittest.mock import MagicMock

import pytest

from haiku.skills.discovery import (
    discover_from_entrypoints,
    discover_from_paths,
    discover_resources,
)
from haiku.skills.models import Skill, SkillMetadata, SkillSource, SkillValidationError

FIXTURES = Path(__file__).parent / "fixtures"


class TestDiscoverFromPaths:
    def test_discovers_skills_in_directory(self):
        skills, errors = discover_from_paths([FIXTURES])
        names = {s.metadata.name for s in skills}
        assert "simple-skill" in names
        assert "skill-with-refs" in names
        assert errors == []

    def test_returns_filesystem_source(self):
        skills, errors = discover_from_paths([FIXTURES])
        for skill in skills:
            assert skill.source == SkillSource.FILESYSTEM
        assert errors == []

    def test_sets_path_to_skill_directory(self):
        skills, errors = discover_from_paths([FIXTURES])
        by_name = {s.metadata.name: s for s in skills}
        assert by_name["simple-skill"].path == FIXTURES / "simple-skill"
        assert errors == []

    def test_instructions_loaded(self):
        skills, errors = discover_from_paths([FIXTURES])
        for skill in skills:
            assert skill.instructions is not None
        assert errors == []

    def test_filesystem_skills_have_no_tools(self):
        skills, errors = discover_from_paths([FIXTURES])
        by_name = {s.metadata.name: s for s in skills}
        assert by_name["simple-skill"].tools == []

    def test_resources_loaded(self):
        skills, errors = discover_from_paths([FIXTURES])
        by_name = {s.metadata.name: s for s in skills}
        assert "references/REFERENCE.md" in by_name["skill-with-refs"].resources
        assert "assets/template.txt" in by_name["skill-with-refs"].resources

    def test_name_must_match_directory(self, tmp_path: Path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: wrong-name\ndescription: Mismatch.\n---\nBody.\n"
        )
        skills, errors = discover_from_paths([tmp_path])
        assert skills == []
        assert len(errors) == 1
        assert "does not match" in str(errors[0])
        assert errors[0].path == skill_dir

    def test_skips_non_skill_entries(self, tmp_path: Path):
        # A file (not a directory) should be skipped
        (tmp_path / "readme.txt").write_text("not a skill")
        # A directory without SKILL.md should be skipped
        (tmp_path / "not-a-skill").mkdir()
        skills, errors = discover_from_paths([tmp_path])
        assert skills == []
        assert errors == []

    def test_nonexistent_path_returns_error(self):
        bad_path = Path("/nonexistent/path")
        skills, errors = discover_from_paths([bad_path])
        assert skills == []
        assert len(errors) == 1
        assert isinstance(errors[0], SkillValidationError)
        assert errors[0].path == bad_path

    def test_path_is_skill_directory(self, tmp_path: Path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: A skill.\n---\nBody.\n"
        )
        skills, errors = discover_from_paths([skill_dir])
        assert len(skills) == 1
        assert skills[0].metadata.name == "my-skill"
        assert skills[0].path == skill_dir
        assert errors == []

    def test_skips_dot_directories(self, tmp_path: Path):
        dot_dir = tmp_path / ".hidden-skill"
        dot_dir.mkdir()
        (dot_dir / "SKILL.md").write_text(
            "---\nname: hidden-skill\ndescription: Hidden.\n---\nBody.\n"
        )
        visible_dir = tmp_path / "visible-skill"
        visible_dir.mkdir()
        (visible_dir / "SKILL.md").write_text(
            "---\nname: visible-skill\ndescription: Visible.\n---\nBody.\n"
        )
        skills, errors = discover_from_paths([tmp_path])
        names = {s.metadata.name for s in skills}
        assert "visible-skill" in names
        assert "hidden-skill" not in names
        assert errors == []

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

        skills, errors = discover_from_paths([dir_a, dir_b])
        names = {s.metadata.name for s in skills}
        assert names == {"skill-a", "skill-b"}
        assert errors == []

    def test_collects_multiple_errors(self, tmp_path: Path):
        # Two broken skills and one valid
        valid = tmp_path / "valid-skill"
        valid.mkdir()
        (valid / "SKILL.md").write_text(
            "---\nname: valid-skill\ndescription: Good.\n---\nBody.\n"
        )

        bad1 = tmp_path / "bad-one"
        bad1.mkdir()
        (bad1 / "SKILL.md").write_text(
            "---\nname: wrong-name\ndescription: Mismatch.\n---\nBody.\n"
        )

        bad2 = tmp_path / "bad-two"
        bad2.mkdir()
        (bad2 / "SKILL.md").write_text(
            "---\nname: also-wrong\ndescription: Mismatch.\n---\nBody.\n"
        )

        skills, errors = discover_from_paths([tmp_path])
        assert len(skills) == 1
        assert skills[0].metadata.name == "valid-skill"
        assert len(errors) == 2
        error_paths = {e.path for e in errors}
        assert error_paths == {bad1, bad2}

    def test_pydantic_validation_error_collected(self, tmp_path: Path):
        skill_dir = tmp_path / "bad-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: BAD-SKILL\ndescription: Invalid name.\n---\nBody.\n"
        )
        skills, errors = discover_from_paths([tmp_path])
        assert skills == []
        assert len(errors) == 1
        assert errors[0].path == skill_dir


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

    def test_excludes_python_files_and_pycache(self, tmp_path: Path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: Test.\n---\nBody.\n"
        )
        (skill_dir / "__init__.py").write_text("# code")
        (skill_dir / "tools.py").write_text("# code")
        pycache = skill_dir / "__pycache__"
        pycache.mkdir()
        (pycache / "__init__.cpython-313.pyc").write_bytes(b"\x00")
        (skill_dir / "config.yaml").write_text("key: value")
        resources = discover_resources(skill_dir)
        assert resources == ["config.yaml"]

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

    def test_excludes_sigstore_bundle(self, tmp_path: Path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: Test.\n---\nBody.\n"
        )
        (skill_dir / "SKILL.sigstore").write_text('{"bundle": "data"}')
        (skill_dir / "config.yaml").write_text("key: value")
        resources = discover_resources(skill_dir)
        assert "SKILL.sigstore" not in resources
        assert "config.yaml" in resources


class TestDiscoverWithVerification:
    def test_verified_true_with_valid_bundle(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from haiku.skills.signing import TrustedIdentity

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
        skills, errors = discover_from_paths([skill_dir], trusted_identities=identities)
        assert len(skills) == 1
        assert skills[0].verified is True
        assert errors == []

    def test_verified_false_without_bundle(self, tmp_path: Path):
        from haiku.skills.signing import TrustedIdentity

        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: Test.\n---\nBody.\n"
        )

        identities = [TrustedIdentity(identity="a@b.com", issuer="https://issuer")]
        skills, errors = discover_from_paths([skill_dir], trusted_identities=identities)
        assert len(skills) == 1
        assert skills[0].verified is False
        assert errors == []

    def test_verification_failure_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from haiku.skills.signing import TrustedIdentity

        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: Test.\n---\nBody.\n"
        )
        (skill_dir / "SKILL.sigstore").write_text('{"bundle": "data"}')

        monkeypatch.setattr(
            "haiku.skills.discovery.verify_skill", lambda *a, **kw: False
        )

        identities = [TrustedIdentity(identity="a@b.com", issuer="https://issuer")]
        skills, errors = discover_from_paths([skill_dir], trusted_identities=identities)
        assert skills == []
        assert len(errors) == 1
        assert "verification failed" in str(errors[0]).lower()

    def test_no_identities_skips_verification(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: Test.\n---\nBody.\n"
        )
        (skill_dir / "SKILL.sigstore").write_text('{"bundle": "data"}')

        skills, errors = discover_from_paths([skill_dir])
        assert len(skills) == 1
        assert skills[0].verified is False
        assert errors == []


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

    def test_auto_populates_resources_from_path(self, monkeypatch: pytest.MonkeyPatch):
        skill = Skill(
            metadata=SkillMetadata(name="ep-skill", description="From entrypoint."),
            source=SkillSource.ENTRYPOINT,
            path=FIXTURES / "skill-with-refs",
        )
        mock_ep = MagicMock()
        mock_ep.load.return_value = lambda: skill

        monkeypatch.setattr(
            "haiku.skills.discovery.entry_points",
            lambda group: [mock_ep],
        )
        skills = discover_from_entrypoints()
        assert len(skills) == 1
        assert "references/REFERENCE.md" in skills[0].resources
        assert "assets/template.txt" in skills[0].resources

    def test_does_not_overwrite_existing_resources(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        skill = Skill(
            metadata=SkillMetadata(name="ep-skill", description="From entrypoint."),
            source=SkillSource.ENTRYPOINT,
            path=FIXTURES / "skill-with-refs",
            resources=["custom.txt"],
        )
        mock_ep = MagicMock()
        mock_ep.load.return_value = lambda: skill

        monkeypatch.setattr(
            "haiku.skills.discovery.entry_points",
            lambda group: [mock_ep],
        )
        skills = discover_from_entrypoints()
        assert skills[0].resources == ["custom.txt"]

    def test_no_resources_without_path(self, monkeypatch: pytest.MonkeyPatch):
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
        assert skills[0].resources == []

    def test_empty_entrypoints(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            "haiku.skills.discovery.entry_points",
            lambda group: [],
        )
        skills = discover_from_entrypoints()
        assert skills == []

    def test_entrypoint_skill_has_factory(self, monkeypatch: pytest.MonkeyPatch):
        def my_factory() -> Skill:
            return Skill(
                metadata=SkillMetadata(name="ep-skill", description="From ep."),
                source=SkillSource.ENTRYPOINT,
            )

        mock_ep = MagicMock()
        mock_ep.load.return_value = my_factory

        monkeypatch.setattr(
            "haiku.skills.discovery.entry_points",
            lambda group: [mock_ep],
        )
        skills = discover_from_entrypoints()
        assert len(skills) == 1
        assert skills[0]._factory is my_factory

    def test_entrypoint_skill_reconfigure(self, monkeypatch: pytest.MonkeyPatch):
        def tool_default(x: int) -> int:
            return x

        def tool_custom(x: int) -> int:
            return x * 2

        def my_factory(mode: str = "default") -> Skill:
            tool = tool_default if mode == "default" else tool_custom
            return Skill(
                metadata=SkillMetadata(name="ep-skill", description="From ep."),
                source=SkillSource.ENTRYPOINT,
                tools=[tool],
            )

        mock_ep = MagicMock()
        mock_ep.load.return_value = my_factory

        monkeypatch.setattr(
            "haiku.skills.discovery.entry_points",
            lambda group: [mock_ep],
        )
        skills = discover_from_entrypoints()
        assert skills[0].tools == [tool_default]

        skills[0].reconfigure(mode="custom")
        assert skills[0].tools == [tool_custom]
