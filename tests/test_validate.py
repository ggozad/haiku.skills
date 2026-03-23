from pathlib import Path

from skills_ref import validate

FIXTURES = Path(__file__).parent / "fixtures"


class TestValidateFixtures:
    def test_simple_skill_valid(self):
        errors = validate(FIXTURES / "simple-skill")
        assert errors == []

    def test_skill_with_refs_valid(self):
        errors = validate(FIXTURES / "skill-with-refs")
        assert errors == []


class TestValidateInvalid:
    def test_nonexistent_path(self):
        errors = validate(Path("/tmp/nonexistent"))
        assert len(errors) > 0

    def test_missing_skill_md(self, tmp_path: Path):
        errors = validate(tmp_path)
        assert len(errors) > 0

    def test_dirname_mismatch(self, tmp_path: Path):
        wrong_dir = tmp_path / "wrong-name"
        wrong_dir.mkdir()
        (wrong_dir / "SKILL.md").write_text(
            "---\nname: actual-name\ndescription: Test.\n---\nBody.\n"
        )
        errors = validate(wrong_dir)
        assert any("wrong-name" in e or "actual-name" in e for e in errors)
