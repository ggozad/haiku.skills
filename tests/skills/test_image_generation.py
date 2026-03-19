"""Tests for the image generation skill package."""

import io
import runpy
from pathlib import Path

import pytest

from haiku.skills.models import SkillSource

from .conftest import SKILLS_ROOT, make_ctx


class TestImageGeneration:
    def test_create_skill(self):
        from haiku_skills_image_generation import create_skill

        skill = create_skill()
        assert skill.metadata.name == "imagegeneration"
        assert (
            skill.metadata.description
            == "Generate images from text prompts using Ollama."
        )
        assert skill.source == SkillSource.ENTRYPOINT
        assert skill.path is not None
        assert skill.instructions is not None
        assert skill.state_type is not None
        assert skill.state_namespace == "imagegeneration"
        assert len(skill.tools) == 1

    @pytest.mark.vcr()
    def test_generate_image(self, tmp_path: Path):
        from haiku_skills_image_generation.imagegeneration.scripts.generate_image import (
            main,
        )

        result = main("a red circle on white background", width=64, height=64)
        assert result.endswith(".png")
        assert Path(result).exists()

    @pytest.mark.vcr()
    def test_generate_image_tool_with_state(self):
        from haiku_skills_image_generation import ImageState, generate_image

        state = ImageState()
        ctx = make_ctx(state)
        result = generate_image(
            ctx, "a red circle on white background", width=64, height=64
        )
        assert result.endswith(".png")
        assert len(state.images) == 1
        assert state.images[0].prompt == "a red circle on white background"
        assert state.images[0].path == result
        assert state.images[0].width == 64
        assert state.images[0].height == 64

    @pytest.mark.vcr()
    def test_main_entry(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            "sys.argv",
            ["generate_image.py", "a red circle on white background", "64", "64"],
        )
        captured = io.StringIO()
        monkeypatch.setattr("sys.stdout", captured)

        script = (
            SKILLS_ROOT
            / "image-generation"
            / "haiku_skills_image_generation"
            / "imagegeneration"
            / "scripts"
            / "generate_image.py"
        )
        runpy.run_path(str(script), run_name="__main__")

        assert captured.getvalue().strip().endswith(".png")
