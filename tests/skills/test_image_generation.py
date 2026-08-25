"""Tests for the image generation skill package."""

from pathlib import Path

import httpx
import pytest

from tests.skills.conftest import make_ctx


class TestImageGeneration:
    def test_create_skill(self):
        from haiku_skills_image_generation import create_skill

        skill = create_skill()
        assert skill.metadata.name == "image-generation"
        assert (
            skill.metadata.description
            == "Generate images from text prompts using Ollama or Atlas Cloud."
        )
        assert skill.instructions is not None
        assert skill.state_type is not None
        assert skill.state_namespace == "image-generation"
        assert len(skill.tools) == 1
        assert skill.path is not None

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

    def test_generate_image_with_atlas(self, monkeypatch):
        from haiku_skills_image_generation import _generate_image

        submitted = []
        polls = iter(
            [
                {"data": {"status": "processing"}},
                {
                    "data": {
                        "status": "completed",
                        "outputs": ["https://cdn.example/generated.png"],
                    }
                },
            ]
        )

        def fake_post(url, **kwargs):
            submitted.append((url, kwargs))
            return _response(url, {"data": {"id": "prediction-1"}})

        def fake_get(url, **kwargs):
            if url == "https://cdn.example/generated.png":
                return httpx.Response(
                    200,
                    content=b"atlas-image",
                    request=httpx.Request("GET", url),
                )
            return _response(url, next(polls))

        monkeypatch.setenv("IMAGE_GENERATION_PROVIDER", "atlas")
        monkeypatch.setenv("ATLASCLOUD_API_KEY", "test-key")
        monkeypatch.setattr(_generate_image.httpx, "post", fake_post)
        monkeypatch.setattr(_generate_image.httpx, "get", fake_get)
        monkeypatch.setattr(_generate_image.time, "sleep", lambda _: None)

        result = Path(_generate_image.main("a red circle", width=1280, height=720))

        assert result.read_bytes() == b"atlas-image"
        assert len(submitted) == 1
        url, kwargs = submitted[0]
        assert url == "https://api.atlascloud.ai/api/v1/model/generateImage"
        assert kwargs["json"] == {
            "model": "google/nano-banana-2-lite/text-to-image-developer",
            "prompt": "a red circle",
            "aspect_ratio": "16:9",
            "resolution": "1k",
        }

    def test_atlas_submit_failure_is_not_retried(self, monkeypatch):
        from haiku_skills_image_generation import _generate_image

        attempts = 0

        def fail_post(url, **kwargs):
            nonlocal attempts
            attempts += 1
            raise httpx.ConnectError("offline", request=httpx.Request("POST", url))

        monkeypatch.setenv("IMAGE_GENERATION_PROVIDER", "atlas")
        monkeypatch.setenv("ATLASCLOUD_API_KEY", "test-key")
        monkeypatch.setattr(_generate_image.httpx, "post", fail_post)

        with pytest.raises(httpx.ConnectError):
            _generate_image.main("a red circle")

        assert attempts == 1


def _response(url: str, data: dict) -> httpx.Response:
    return httpx.Response(
        200,
        json=data,
        request=httpx.Request("GET", url),
    )
