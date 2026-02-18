"""Tests for distributable skill packages."""

import io
import json
import runpy
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic_ai import RunContext

from haiku.skills.models import SkillSource
from haiku.skills.state import SkillRunDeps

SKILLS_ROOT = Path(__file__).parent.parent / "skills"


@pytest.fixture(scope="module")
def vcr_config():
    return {
        "ignore_localhost": False,
        "filter_headers": ["authorization", "x-api-key", "x-subscription-token"],
        "decode_compressed_response": True,
    }


def _make_ctx(state=None):
    """Create a mock RunContext with SkillRunDeps."""
    ctx = MagicMock(spec=RunContext)
    ctx.deps = SkillRunDeps(state=state)
    return ctx


class TestWeb:
    def test_create_skill(self):
        from haiku_skills_web import create_skill

        skill = create_skill()
        assert skill.metadata.name == "web"
        assert skill.metadata.description == "Search the web and fetch page content."
        assert skill.source == SkillSource.ENTRYPOINT
        assert skill.path is not None
        assert skill.instructions is not None
        assert skill.state_type is not None
        assert skill.state_namespace == "web"
        assert len(skill.tools) == 2

    @pytest.mark.vcr()
    def test_search(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BRAVE_API_KEY", "test-key-for-vcr-playback")
        from haiku_skills_web.scripts.search import main

        result = main("pydantic ai framework", count=2)
        assert "URL:" in result
        assert "---" in result

    def test_search_no_api_key(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("BRAVE_API_KEY", raising=False)
        from haiku_skills_web.scripts.search import main

        result = main("test")
        assert result == "Error: BRAVE_API_KEY not set."

    def test_search_main_entry(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BRAVE_API_KEY", "")
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"query": "test"})))
        captured = io.StringIO()
        monkeypatch.setattr("sys.stdout", captured)

        script = SKILLS_ROOT / "web" / "haiku_skills_web" / "scripts" / "search.py"
        runpy.run_path(str(script), run_name="__main__")

        output = json.loads(captured.getvalue())
        assert "BRAVE_API_KEY not set" in output["result"]

    @pytest.mark.vcr()
    def test_search_tool_with_state(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BRAVE_API_KEY", "test-key-for-vcr-playback")
        from haiku_skills_web import WebState, search

        state = WebState()
        ctx = _make_ctx(state)
        result = search(ctx, "pydantic ai framework", count=2)
        assert "URL:" in result
        assert "pydantic ai framework" in state.searches
        assert len(state.searches["pydantic ai framework"]) > 0

    def test_search_tool_no_api_key(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("BRAVE_API_KEY", raising=False)
        from haiku_skills_web import search

        ctx = _make_ctx()
        result = search(ctx, "test")
        assert "Error:" in result

    def test_fetch_page(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_web.scripts.fetch_page as fp

        html = (
            "<html><body>"
            "<article><p>Pydantic AI is a Python agent framework.</p></article>"
            "</body></html>"
        )
        monkeypatch.setattr(fp.trafilatura, "fetch_url", lambda url: html)
        from haiku_skills_web.scripts.fetch_page import main

        result = main("https://ai.pydantic.dev/")
        assert "pydantic" in result.lower()

    def test_fetch_page_invalid_url(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_web.scripts.fetch_page as fp

        monkeypatch.setattr(fp.trafilatura, "fetch_url", lambda url: None)
        from haiku_skills_web.scripts.fetch_page import main

        result = main("https://invalid.example.com")
        assert result == "Error: could not fetch the page."

    def test_fetch_page_no_content(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_web.scripts.fetch_page as fp

        monkeypatch.setattr(fp.trafilatura, "fetch_url", lambda url: "<html></html>")
        monkeypatch.setattr(fp, "extract", lambda *a, **kw: None)
        from haiku_skills_web.scripts.fetch_page import main

        result = main("https://example.com")
        assert result == "Error: could not extract content from the page."

    def test_fetch_page_main_entry(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_web.scripts.fetch_page as fp

        monkeypatch.setattr(fp.trafilatura, "fetch_url", lambda url: None)
        monkeypatch.setattr(
            "sys.stdin",
            io.StringIO(json.dumps({"url": "https://invalid.example.com"})),
        )
        captured = io.StringIO()
        monkeypatch.setattr("sys.stdout", captured)

        script = SKILLS_ROOT / "web" / "haiku_skills_web" / "scripts" / "fetch_page.py"
        runpy.run_path(str(script), run_name="__main__")

        output = json.loads(captured.getvalue())
        assert "could not fetch" in output["result"]

    def test_fetch_page_tool_with_state(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_web.scripts.fetch_page as fp

        html = "<html><body><article><p>Test content here.</p></article></body></html>"
        monkeypatch.setattr(fp.trafilatura, "fetch_url", lambda url: html)
        from haiku_skills_web import WebState, fetch_page

        state = WebState()
        ctx = _make_ctx(state)
        result = fetch_page(ctx, "https://example.com")
        assert "test content" in result.lower()
        assert "https://example.com" in state.pages
        assert state.pages["https://example.com"].content == result

    def test_fetch_page_tool_error_no_state(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_web.scripts.fetch_page as fp

        monkeypatch.setattr(fp.trafilatura, "fetch_url", lambda url: None)
        from haiku_skills_web import WebState, fetch_page

        state = WebState()
        ctx = _make_ctx(state)
        result = fetch_page(ctx, "https://invalid.example.com")
        assert result.startswith("Error:")
        assert len(state.pages) == 0


class TestImageGeneration:
    def test_create_skill(self):
        from haiku_skills_image_generation import create_skill

        skill = create_skill()
        assert skill.metadata.name == "image-generation"
        assert (
            skill.metadata.description
            == "Generate images from text prompts using Ollama."
        )
        assert skill.source == SkillSource.ENTRYPOINT
        assert skill.path is not None
        assert skill.instructions is not None
        assert skill.state_type is not None
        assert skill.state_namespace == "image-generation"
        assert len(skill.tools) == 1

    @pytest.mark.vcr()
    def test_generate_image(self, tmp_path: Path):
        from haiku_skills_image_generation.scripts.generate_image import main

        result = main("a red circle on white background", width=64, height=64)
        assert result.startswith("![")
        assert result.endswith(")")

    @pytest.mark.vcr()
    def test_generate_image_tool_with_state(self):
        from haiku_skills_image_generation import ImageState, generate_image

        state = ImageState()
        ctx = _make_ctx(state)
        result = generate_image(
            ctx, "a red circle on white background", width=64, height=64
        )
        assert result.startswith("![")
        assert len(state.images) == 1
        assert state.images[0].prompt == "a red circle on white background"
        assert state.images[0].width == 64
        assert state.images[0].height == 64

    @pytest.mark.vcr()
    def test_main_entry(self, monkeypatch: pytest.MonkeyPatch):
        input_data = json.dumps(
            {"prompt": "a red circle on white background", "width": 64, "height": 64}
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(input_data))
        captured = io.StringIO()
        monkeypatch.setattr("sys.stdout", captured)

        script = (
            SKILLS_ROOT
            / "image-generation"
            / "haiku_skills_image_generation"
            / "scripts"
            / "generate_image.py"
        )
        runpy.run_path(str(script), run_name="__main__")

        output = json.loads(captured.getvalue())
        assert "![" in output["result"]


class TestCodeExecution:
    def test_create_skill(self):
        from haiku_skills_code_execution import create_skill

        skill = create_skill()
        assert skill.metadata.name == "code-execution"
        assert (
            skill.metadata.description
            == "Write and execute Python code to solve tasks."
        )
        assert skill.source == SkillSource.ENTRYPOINT
        assert skill.path is not None
        assert skill.instructions is not None
        assert skill.state_type is not None
        assert skill.state_namespace == "code-execution"
        assert len(skill.tools) == 1

    def test_run_code_with_output(self):
        from haiku_skills_code_execution.scripts.run_code import main

        result = main("print(1 + 1)")
        assert "```python" in result
        assert "print(1 + 1)" in result
        assert "2" in result

    def test_run_code_with_result(self):
        from haiku_skills_code_execution.scripts.run_code import main

        result = main("1 + 1")
        assert "result: 2" in result

    def test_run_code_no_output(self):
        from haiku_skills_code_execution.scripts.run_code import main

        result = main("x = 1")
        assert "no output" in result.lower()

    def test_run_code_tool_with_state(self):
        from haiku_skills_code_execution import CodeState, run_code

        state = CodeState()
        ctx = _make_ctx(state)
        result = run_code(ctx, "print(1 + 1)")
        assert "2" in result
        assert len(state.executions) == 1
        assert state.executions[0].code == "print(1 + 1)"
        assert state.executions[0].success is True

    def test_run_code_tool_with_result_value(self):
        from haiku_skills_code_execution import CodeState, run_code

        state = CodeState()
        ctx = _make_ctx(state)
        result = run_code(ctx, "1 + 1")
        assert "result: 2" in result
        assert len(state.executions) == 1
        assert state.executions[0].result == "2"

    def test_run_code_tool_no_output(self):
        from haiku_skills_code_execution import CodeState, run_code

        state = CodeState()
        ctx = _make_ctx(state)
        result = run_code(ctx, "x = 1")
        assert "no output" in result.lower()
        assert len(state.executions) == 1

    def test_main_entry(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"code": "1 + 1"})))
        captured = io.StringIO()
        monkeypatch.setattr("sys.stdout", captured)

        script = (
            SKILLS_ROOT
            / "code-execution"
            / "haiku_skills_code_execution"
            / "scripts"
            / "run_code.py"
        )
        runpy.run_path(str(script), run_name="__main__")

        output = json.loads(captured.getvalue())
        assert "result" in output
