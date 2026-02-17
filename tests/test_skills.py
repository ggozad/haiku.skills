"""Tests for distributable skill packages."""

import io
import json
import runpy
from pathlib import Path

import pytest

from haiku.skills.models import SkillSource

SKILLS_ROOT = Path(__file__).parent.parent / "skills"


@pytest.fixture(scope="module")
def vcr_config():
    return {
        "ignore_localhost": False,
        "filter_headers": ["authorization", "x-api-key", "x-subscription-token"],
        "decode_compressed_response": True,
    }


class TestWeb:
    def test_create_skill(self):
        from haiku_skills_web import create_skill

        skill = create_skill()
        assert skill.metadata.name == "web"
        assert skill.metadata.description == "Search the web and fetch page content."
        assert skill.source == SkillSource.ENTRYPOINT
        assert skill.path is not None

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

    @pytest.mark.vcr()
    def test_generate_image(self, tmp_path: Path):
        from haiku_skills_image_generation.scripts.generate_image import main

        result = main("a red circle on white background", width=64, height=64)
        assert result.startswith("![")
        assert result.endswith(")")

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
