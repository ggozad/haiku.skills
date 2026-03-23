"""Tests for the image generation skill package."""

from pathlib import Path

import pytest

from .conftest import make_ctx


class TestImageGeneration:
    def test_create_skill(self):
        from haiku_skills_image_generation import create_skill

        skill = create_skill()
        assert skill.metadata.name == "image-generation"
        assert (
            skill.metadata.description
            == "Generate images from text prompts using Ollama."
        )
        assert skill.instructions is not None
        assert skill.state_type is not None
        assert skill.state_namespace == "image-generation"
        assert len(skill.tools) == 1

    @pytest.mark.vcr()
    def test_generate_image(self, tmp_path: Path):
        from haiku_skills_image_generation._generate_image import main

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
