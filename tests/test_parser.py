from pathlib import Path

import pytest

from haiku.skills.parser import parse_skill_md

FIXTURES = Path(__file__).parent / "fixtures"


class TestParseSkillMd:
    def test_simple_skill(self):
        path = FIXTURES / "simple-skill" / "SKILL.md"
        metadata, body = parse_skill_md(path)
        assert metadata.name == "simple-skill"
        assert metadata.description == "A simple test skill that does basic operations."
        assert metadata.license is None
        assert metadata.allowed_tools == []
        assert "# Simple Skill" in body
        assert "Read the input" in body

    def test_skill_with_all_fields(self):
        path = FIXTURES / "skill-with-refs" / "SKILL.md"
        metadata, body = parse_skill_md(path)
        assert metadata.name == "skill-with-refs"
        assert metadata.license == "MIT"
        assert metadata.compatibility == "Requires network access"
        assert metadata.metadata == {"author": "test-org", "version": "1.0"}
        assert metadata.allowed_tools == ["Bash(git:*)", "Read", "Write"]
        assert "# Skill With References" in body

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            parse_skill_md(Path("/nonexistent/SKILL.md"))

    def test_missing_name_raises(self, tmp_path: Path):
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("---\ndescription: No name.\n---\nBody.\n")
        with pytest.raises(ValueError, match="name"):
            parse_skill_md(skill_md)

    def test_missing_description_raises(self, tmp_path: Path):
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("---\nname: test\n---\nBody.\n")
        with pytest.raises(ValueError, match="description"):
            parse_skill_md(skill_md)

    def test_missing_frontmatter_raises(self, tmp_path: Path):
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("# Just markdown, no frontmatter\n")
        with pytest.raises(ValueError, match="frontmatter"):
            parse_skill_md(skill_md)

    def test_unclosed_frontmatter_raises(self, tmp_path: Path):
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("---\nname: test\n")
        with pytest.raises(ValueError, match="frontmatter"):
            parse_skill_md(skill_md)

    def test_invalid_frontmatter_raises(self, tmp_path: Path):
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("---\njust a string\n---\nBody.\n")
        with pytest.raises(ValueError, match="invalid frontmatter"):
            parse_skill_md(skill_md)

    def test_allowed_tools_parsed_from_string(self, tmp_path: Path):
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text(
            "---\nname: test\ndescription: Test.\nallowed-tools: Read Write\n---\nBody.\n"
        )
        metadata, _ = parse_skill_md(skill_md)
        assert metadata.allowed_tools == ["Read", "Write"]

    def test_allowed_tools_parsed_from_yaml_list(self, tmp_path: Path):
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text(
            "---\nname: test\ndescription: Test.\n"
            "allowed-tools:\n  - Read\n  - Write\n---\nBody.\n"
        )
        metadata, _ = parse_skill_md(skill_md)
        assert metadata.allowed_tools == ["Read", "Write"]
