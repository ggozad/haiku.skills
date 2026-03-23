"""Tests for the web skill package."""

import pytest

from tests.skills.conftest import make_ctx


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
        assert skill.instructions is not None
        assert skill.state_type is not None
        assert skill.state_namespace == "web"
        assert len(skill.tools) == 2

    @pytest.mark.vcr()
    def test_search(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BRAVE_API_KEY", "test-key-for-vcr-playback")
        from haiku_skills_web._search import main

        result = main("pydantic ai framework", count=2)
        assert "URL:" in result
        assert "---" in result

    def test_search_no_api_key(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("BRAVE_API_KEY", raising=False)
        from haiku_skills_web._search import main

        result = main("test")
        assert result == "Error: BRAVE_API_KEY not set."

    @pytest.mark.vcr()
    def test_search_tool_with_state(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BRAVE_API_KEY", "test-key-for-vcr-playback")
        from haiku_skills_web import WebState, search

        state = WebState()
        ctx = make_ctx(state)
        result = search(ctx, "pydantic ai framework", count=2)
        assert "URL:" in result
        assert "pydantic ai framework" in state.searches
        assert len(state.searches["pydantic ai framework"]) > 0

    def test_search_tool_no_api_key(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("BRAVE_API_KEY", raising=False)
        from haiku_skills_web import search

        ctx = make_ctx()
        result = search(ctx, "test")
        assert "Error:" in result

    def test_fetch_page(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_web._fetch_page as fp

        html = (
            "<html><body>"
            "<article><p>Pydantic AI is a Python agent framework.</p></article>"
            "</body></html>"
        )
        response = _make_fetch_response(
            html.encode(), "text/html", "https://ai.pydantic.dev/"
        )
        monkeypatch.setattr(fp, "fetch_response", lambda *a, **kw: response)
        from haiku_skills_web._fetch_page import main

        result = main("https://ai.pydantic.dev/")
        assert "pydantic" in result.lower()

    def test_fetch_page_invalid_url(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_web._fetch_page as fp

        monkeypatch.setattr(fp, "fetch_response", lambda *a, **kw: None)
        from haiku_skills_web._fetch_page import main

        result = main("https://invalid.example.com")
        assert result == "Error: could not fetch the page."

    def test_fetch_page_no_content(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_web._fetch_page as fp

        response = _make_fetch_response(
            b"<html></html>", "text/html; charset=utf-8", "https://example.com"
        )
        monkeypatch.setattr(fp, "fetch_response", lambda *a, **kw: response)
        monkeypatch.setattr(fp, "extract", lambda *a, **kw: None)
        from haiku_skills_web._fetch_page import main

        result = main("https://example.com")
        assert result == "Error: could not extract content from the page."

    def test_fetch_page_plain_text(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_web._fetch_page as fp

        text = "# README\n\nThis is plain markdown content."
        response = _make_fetch_response(
            text.encode(), "text/plain; charset=utf-8", "https://example.com/README.md"
        )
        monkeypatch.setattr(fp, "fetch_response", lambda *a, **kw: response)
        from haiku_skills_web._fetch_page import main

        result = main("https://example.com/README.md")
        assert result == text

    def test_fetch_page_tool_with_state(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_web._fetch_page as fp

        html = "<html><body><article><p>Test content here.</p></article></body></html>"
        response = _make_fetch_response(
            html.encode(), "text/html", "https://example.com"
        )
        monkeypatch.setattr(fp, "fetch_response", lambda *a, **kw: response)
        from haiku_skills_web import WebState, fetch_page

        state = WebState()
        ctx = make_ctx(state)
        result = fetch_page(ctx, "https://example.com")
        assert "test content" in result.lower()
        assert "https://example.com" in state.pages
        assert state.pages["https://example.com"].content == result

    def test_fetch_page_tool_error_no_state(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_web._fetch_page as fp

        monkeypatch.setattr(fp, "fetch_response", lambda *a, **kw: None)
        from haiku_skills_web import WebState, fetch_page

        state = WebState()
        ctx = make_ctx(state)
        result = fetch_page(ctx, "https://invalid.example.com")
        assert result.startswith("Error:")
        assert len(state.pages) == 0
