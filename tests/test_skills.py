"""Tests for distributable skill packages."""

import io
import runpy
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

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


def _make_fetch_response(data: bytes, content_type: str, url: str):
    """Create a mock trafilatura Response with headers."""
    from trafilatura.downloads import Response

    response = Response(data=data, status=200, url=url)
    response.store_headers({"Content-Type": content_type})
    response.decode_data(True)
    return response


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
        monkeypatch.setattr("sys.argv", ["search.py", "test"])
        captured = io.StringIO()
        monkeypatch.setattr("sys.stdout", captured)

        script = SKILLS_ROOT / "web" / "haiku_skills_web" / "scripts" / "search.py"
        runpy.run_path(str(script), run_name="__main__")

        assert "BRAVE_API_KEY not set" in captured.getvalue()

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
        response = _make_fetch_response(
            html.encode(), "text/html", "https://ai.pydantic.dev/"
        )
        monkeypatch.setattr(fp, "fetch_response", lambda *a, **kw: response)
        from haiku_skills_web.scripts.fetch_page import main

        result = main("https://ai.pydantic.dev/")
        assert "pydantic" in result.lower()

    def test_fetch_page_invalid_url(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_web.scripts.fetch_page as fp

        monkeypatch.setattr(fp, "fetch_response", lambda *a, **kw: None)
        from haiku_skills_web.scripts.fetch_page import main

        result = main("https://invalid.example.com")
        assert result == "Error: could not fetch the page."

    def test_fetch_page_no_content(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_web.scripts.fetch_page as fp

        response = _make_fetch_response(
            b"<html></html>", "text/html; charset=utf-8", "https://example.com"
        )
        monkeypatch.setattr(fp, "fetch_response", lambda *a, **kw: response)
        monkeypatch.setattr(fp, "extract", lambda *a, **kw: None)
        from haiku_skills_web.scripts.fetch_page import main

        result = main("https://example.com")
        assert result == "Error: could not extract content from the page."

    def test_fetch_page_plain_text(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_web.scripts.fetch_page as fp

        text = "# README\n\nThis is plain markdown content."
        response = _make_fetch_response(
            text.encode(), "text/plain; charset=utf-8", "https://example.com/README.md"
        )
        monkeypatch.setattr(fp, "fetch_response", lambda *a, **kw: response)
        from haiku_skills_web.scripts.fetch_page import main

        result = main("https://example.com/README.md")
        assert result == text

    def test_fetch_page_main_entry(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_web.scripts.fetch_page as fp

        monkeypatch.setattr(fp, "fetch_response", lambda *a, **kw: None)
        monkeypatch.setattr(
            "sys.argv", ["fetch_page.py", "https://invalid.example.com"]
        )
        captured = io.StringIO()
        monkeypatch.setattr("sys.stdout", captured)

        script = SKILLS_ROOT / "web" / "haiku_skills_web" / "scripts" / "fetch_page.py"
        runpy.run_path(str(script), run_name="__main__")

        assert "could not fetch" in captured.getvalue()

    def test_fetch_page_tool_with_state(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_web.scripts.fetch_page as fp

        html = "<html><body><article><p>Test content here.</p></article></body></html>"
        response = _make_fetch_response(
            html.encode(), "text/html", "https://example.com"
        )
        monkeypatch.setattr(fp, "fetch_response", lambda *a, **kw: response)
        from haiku_skills_web import WebState, fetch_page

        state = WebState()
        ctx = _make_ctx(state)
        result = fetch_page(ctx, "https://example.com")
        assert "test content" in result.lower()
        assert "https://example.com" in state.pages
        assert state.pages["https://example.com"].content == result

    def test_fetch_page_tool_error_no_state(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_web.scripts.fetch_page as fp

        monkeypatch.setattr(fp, "fetch_response", lambda *a, **kw: None)
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
            / "scripts"
            / "generate_image.py"
        )
        runpy.run_path(str(script), run_name="__main__")

        assert "![" in captured.getvalue()


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
        monkeypatch.setattr("sys.argv", ["run_code.py", "1 + 1"])
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

        assert "result" in captured.getvalue()


class TestGraphitiMemory:
    @pytest.fixture(autouse=True)
    def _reset_globals(self, monkeypatch: pytest.MonkeyPatch):
        """Reset module-level singleton state between tests."""
        import haiku_skills_graphiti_memory as mod

        monkeypatch.setattr(mod, "_client", None)
        monkeypatch.setattr(mod, "_initialized", False)

    def _mock_client(self) -> AsyncMock:
        client = AsyncMock()
        client.build_indices_and_constraints = AsyncMock()
        client.add_episode = AsyncMock()
        client.search = AsyncMock(return_value=[])
        client.driver = MagicMock()
        return client

    def test_create_skill(self):
        from haiku_skills_graphiti_memory import create_skill

        skill = create_skill()
        assert skill.metadata.name == "graphiti-memory"
        assert (
            skill.metadata.description
            == "Store and recall memories using a knowledge graph."
        )
        assert skill.source == SkillSource.ENTRYPOINT
        assert skill.path is not None
        assert skill.instructions is not None
        assert skill.state_type is not None
        assert skill.state_namespace == "graphiti-memory"
        assert len(skill.tools) == 3

    async def test_remember(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_graphiti_memory as mod
        from haiku_skills_graphiti_memory import MemoryState, remember

        client = self._mock_client()
        monkeypatch.setattr(mod, "_get_client", AsyncMock(return_value=client))

        state = MemoryState()
        ctx = _make_ctx(state)
        result = await remember(ctx, "Yiorgis likes coffee", name="preference")

        assert "Remembered: Yiorgis likes coffee" in result
        client.add_episode.assert_called_once()
        call_kwargs = client.add_episode.call_args.kwargs
        assert call_kwargs["name"] == "preference"
        assert call_kwargs["episode_body"] == "Yiorgis likes coffee"
        assert call_kwargs["source_description"] == "agent observation"
        assert call_kwargs["group_id"] == "default"
        assert len(state.memories) == 1
        assert state.memories[0].name == "preference"
        assert state.memories[0].content == "Yiorgis likes coffee"

    async def test_remember_error(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_graphiti_memory as mod
        from haiku_skills_graphiti_memory import MemoryState, remember

        client = self._mock_client()
        client.add_episode.side_effect = RuntimeError("connection failed")
        monkeypatch.setattr(mod, "_get_client", AsyncMock(return_value=client))

        state = MemoryState()
        ctx = _make_ctx(state)
        result = await remember(ctx, "some fact")

        assert result.startswith("Error:")
        assert "connection failed" in result
        assert len(state.memories) == 0

    async def test_recall(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_graphiti_memory as mod
        from haiku_skills_graphiti_memory import MemoryState, recall

        edge1 = MagicMock()
        edge1.fact = "Yiorgis likes coffee"
        edge2 = MagicMock()
        edge2.fact = "Yiorgis works on haiku.skills"

        client = self._mock_client()
        client.search = AsyncMock(return_value=[edge1, edge2])
        monkeypatch.setattr(mod, "_get_client", AsyncMock(return_value=client))

        state = MemoryState()
        ctx = _make_ctx(state)
        result = await recall(ctx, "what does Yiorgis like?")

        assert "- Yiorgis likes coffee" in result
        assert "- Yiorgis works on haiku.skills" in result
        client.search.assert_called_once()
        call_kwargs = client.search.call_args.kwargs
        assert call_kwargs["query"] == "what does Yiorgis like?"
        assert call_kwargs["group_ids"] == ["default"]
        assert call_kwargs["num_results"] == 10
        assert len(state.recalls) == 1
        assert state.recalls[0].query == "what does Yiorgis like?"
        assert len(state.recalls[0].facts) == 2

    async def test_recall_no_results(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_graphiti_memory as mod
        from haiku_skills_graphiti_memory import MemoryState, recall

        client = self._mock_client()
        client.search = AsyncMock(return_value=[])
        monkeypatch.setattr(mod, "_get_client", AsyncMock(return_value=client))

        state = MemoryState()
        ctx = _make_ctx(state)
        result = await recall(ctx, "nonexistent topic")

        assert result == "No memories found for: nonexistent topic"
        assert len(state.recalls) == 1
        assert state.recalls[0].facts == []

    async def test_recall_error(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_graphiti_memory as mod
        from haiku_skills_graphiti_memory import recall

        client = self._mock_client()
        client.search.side_effect = RuntimeError("search failed")
        monkeypatch.setattr(mod, "_get_client", AsyncMock(return_value=client))

        ctx = _make_ctx()
        result = await recall(ctx, "test")

        assert result.startswith("Error:")
        assert "search failed" in result

    async def test_forget(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_graphiti_memory as mod
        from haiku_skills_graphiti_memory import forget

        edge1 = AsyncMock()
        edge1.fact = "outdated fact 1"
        edge2 = AsyncMock()
        edge2.fact = "outdated fact 2"

        client = self._mock_client()
        client.search = AsyncMock(return_value=[edge1, edge2])
        monkeypatch.setattr(mod, "_get_client", AsyncMock(return_value=client))

        ctx = _make_ctx()
        result = await forget(ctx, "outdated info")

        assert "Deleted memories:" in result
        assert "- outdated fact 1" in result
        assert "- outdated fact 2" in result
        edge1.delete.assert_called_once_with(client.driver)
        edge2.delete.assert_called_once_with(client.driver)

    async def test_forget_no_results(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_graphiti_memory as mod
        from haiku_skills_graphiti_memory import forget

        client = self._mock_client()
        client.search = AsyncMock(return_value=[])
        monkeypatch.setattr(mod, "_get_client", AsyncMock(return_value=client))

        ctx = _make_ctx()
        result = await forget(ctx, "nothing here")

        assert result == "No matching memories found for: nothing here"

    async def test_forget_error(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_graphiti_memory as mod
        from haiku_skills_graphiti_memory import forget

        client = self._mock_client()
        client.search.side_effect = RuntimeError("search failed")
        monkeypatch.setattr(mod, "_get_client", AsyncMock(return_value=client))

        ctx = _make_ctx()
        result = await forget(ctx, "test")

        assert result.startswith("Error:")
        assert "search failed" in result

    async def test_get_client_lazy_init(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_graphiti_memory as mod

        monkeypatch.delenv("GRAPHITI_GROUP_ID", raising=False)

        mock_driver_cls = MagicMock()
        mock_graphiti_cls = MagicMock()
        mock_client = AsyncMock()
        mock_graphiti_cls.return_value = mock_client

        import graphiti_core
        import graphiti_core.driver.falkordb_driver as falkor_mod

        monkeypatch.setattr(graphiti_core, "Graphiti", mock_graphiti_cls)
        monkeypatch.setattr(falkor_mod, "FalkorDriver", mock_driver_cls)
        monkeypatch.setattr(mod, "_build_llm_client", lambda: "llm")
        monkeypatch.setattr(mod, "_build_embedder", lambda: "embedder")
        monkeypatch.setattr(mod, "_build_cross_encoder", lambda: "cross_encoder")

        client1 = await mod._get_client()
        client2 = await mod._get_client()

        assert client1 is client2
        mock_graphiti_cls.assert_called_once()
        call_kwargs = mock_graphiti_cls.call_args.kwargs
        assert call_kwargs["llm_client"] == "llm"
        assert call_kwargs["embedder"] == "embedder"
        assert call_kwargs["cross_encoder"] == "cross_encoder"
        assert mock_driver_cls.call_args.kwargs["database"] == "default"
        mock_client.build_indices_and_constraints.assert_called_once()

    async def test_get_client_env_vars(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_graphiti_memory as mod

        monkeypatch.setenv("FALKORDB_URI", "falkor://myuser:mypass@myhost:1234")
        monkeypatch.setenv("GRAPHITI_GROUP_ID", "my-tenant")

        mock_driver_cls = MagicMock()
        mock_graphiti_cls = MagicMock()
        mock_client = AsyncMock()
        mock_graphiti_cls.return_value = mock_client

        import graphiti_core
        import graphiti_core.driver.falkordb_driver as falkor_mod

        monkeypatch.setattr(graphiti_core, "Graphiti", mock_graphiti_cls)
        monkeypatch.setattr(falkor_mod, "FalkorDriver", mock_driver_cls)
        monkeypatch.setattr(mod, "_build_llm_client", lambda: "llm")
        monkeypatch.setattr(mod, "_build_embedder", lambda: "embedder")
        monkeypatch.setattr(mod, "_build_cross_encoder", lambda: "cross_encoder")

        await mod._get_client()

        driver_kwargs = mock_driver_cls.call_args.kwargs
        assert driver_kwargs["host"] == "myhost"
        assert driver_kwargs["port"] == 1234
        assert driver_kwargs["username"] == "myuser"
        assert driver_kwargs["password"] == "mypass"
        assert driver_kwargs["database"] == "my-tenant"

    def test_build_llm_client_defaults(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
        monkeypatch.delenv("GRAPHITI_LLM_MODEL", raising=False)
        monkeypatch.delenv("GRAPHITI_SMALL_LLM_MODEL", raising=False)

        from haiku_skills_graphiti_memory import _build_llm_client

        client = _build_llm_client()
        assert client.config.model == "gpt-oss"
        assert client.config.small_model == "gpt-oss"
        assert client.config.base_url == "http://localhost:11434/v1"

    def test_build_llm_client_env_vars(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://myhost:9999")
        monkeypatch.setenv("GRAPHITI_LLM_MODEL", "llama3")
        monkeypatch.setenv("GRAPHITI_SMALL_LLM_MODEL", "llama3-small")

        from haiku_skills_graphiti_memory import _build_llm_client

        client = _build_llm_client()
        assert client.config.model == "llama3"
        assert client.config.small_model == "llama3-small"
        assert client.config.base_url == "http://myhost:9999/v1"

    def test_build_embedder_defaults(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
        monkeypatch.delenv("GRAPHITI_EMBEDDING_MODEL", raising=False)
        monkeypatch.delenv("GRAPHITI_EMBEDDING_DIM", raising=False)

        from haiku_skills_graphiti_memory import _build_embedder

        embedder = _build_embedder()
        assert embedder.config.embedding_model == "qwen3-embedding:4b"
        assert embedder.config.embedding_dim == 2560
        assert embedder.config.base_url == "http://localhost:11434/v1"

    def test_build_embedder_env_vars(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://myhost:9999")
        monkeypatch.setenv("GRAPHITI_EMBEDDING_MODEL", "nomic-embed-text")
        monkeypatch.setenv("GRAPHITI_EMBEDDING_DIM", "768")

        from haiku_skills_graphiti_memory import _build_embedder

        embedder = _build_embedder()
        assert embedder.config.embedding_model == "nomic-embed-text"
        assert embedder.config.embedding_dim == 768
        assert embedder.config.base_url == "http://myhost:9999/v1"

    def test_build_cross_encoder(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
        monkeypatch.delenv("GRAPHITI_LLM_MODEL", raising=False)
        monkeypatch.delenv("GRAPHITI_SMALL_LLM_MODEL", raising=False)

        from haiku_skills_graphiti_memory import _build_cross_encoder

        cross_encoder = _build_cross_encoder()
        assert cross_encoder.config.model == "gpt-oss"

    def test_parse_falkordb_uri(self):
        from haiku_skills_graphiti_memory import _parse_falkordb_uri

        result = _parse_falkordb_uri("falkor://localhost:6379")
        assert result == {"host": "localhost", "port": 6379}

        result = _parse_falkordb_uri("falkor://user:pass@host:1234")
        assert result == {
            "host": "host",
            "port": 1234,
            "username": "user",
            "password": "pass",
        }

        result = _parse_falkordb_uri("falkor://host:9999")
        assert result == {"host": "host", "port": 9999}

    def test_get_group_id_default(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("GRAPHITI_GROUP_ID", raising=False)
        from haiku_skills_graphiti_memory import _get_group_id

        assert _get_group_id() == "default"

    def test_get_group_id_from_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("GRAPHITI_GROUP_ID", "my-tenant")
        from haiku_skills_graphiti_memory import _get_group_id

        assert _get_group_id() == "my-tenant"
