"""Tests for distributable skill packages."""

import io
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
        assert result.endswith(".png")
        assert Path(result).exists()

    @pytest.mark.vcr()
    def test_generate_image_tool_with_state(self):
        from haiku_skills_image_generation import ImageState, generate_image

        state = ImageState()
        ctx = _make_ctx(state)
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
            / "scripts"
            / "generate_image.py"
        )
        runpy.run_path(str(script), run_name="__main__")

        assert captured.getvalue().strip().endswith(".png")


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


class TestEmail:
    @pytest.fixture(autouse=True)
    def _reset_globals(self, monkeypatch: pytest.MonkeyPatch):
        """Reset module-level singleton state between tests."""
        import haiku_skills_gmail as mod

        monkeypatch.setattr(mod, "_service", None)

    def test_create_skill(self):
        from haiku_skills_gmail import create_skill

        skill = create_skill()
        assert skill.metadata.name == "gmail"
        assert (
            skill.metadata.description == "Search, read, send, and manage Gmail emails."
        )
        assert skill.source == SkillSource.ENTRYPOINT
        assert skill.path is not None
        assert skill.instructions is not None
        assert skill.state_type is not None
        assert skill.state_namespace == "gmail"
        assert len(skill.tools) == 2

    # -- Config --

    def test_credentials_path_default(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("EMAIL_CREDENTIALS_PATH", raising=False)
        from haiku_skills_gmail import _credentials_path

        result = _credentials_path()
        assert (
            result
            == Path.home() / ".config" / "haiku-skills-gmail" / "credentials.json"
        )

    def test_credentials_path_from_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("EMAIL_CREDENTIALS_PATH", "/tmp/my-creds.json")
        from haiku_skills_gmail import _credentials_path

        assert _credentials_path() == Path("/tmp/my-creds.json")

    def test_token_path_default(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("EMAIL_TOKEN_PATH", raising=False)
        from haiku_skills_gmail import _token_path

        result = _token_path()
        assert result == Path.home() / ".config" / "haiku-skills-gmail" / "token.json"

    def test_token_path_from_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("EMAIL_TOKEN_PATH", "/tmp/my-token.json")
        from haiku_skills_gmail import _token_path

        assert _token_path() == Path("/tmp/my-token.json")

    # -- Auth --

    def test_get_service_cached(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_gmail as mod

        sentinel = MagicMock()
        monkeypatch.setattr(mod, "_service", sentinel)

        result = mod._get_service()
        assert result is sentinel

    def test_get_service_no_credentials_file(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_gmail as mod

        monkeypatch.setattr(
            mod, "_credentials_path", lambda: Path("/nonexistent/creds.json")
        )

        with pytest.raises(FileNotFoundError, match="credentials.json"):
            mod._get_service()

    def test_get_service_from_token(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        import haiku_skills_gmail as mod

        token_file = tmp_path / "token.json"
        token_file.write_text("{}")
        creds_file = tmp_path / "credentials.json"
        creds_file.write_text("{}")

        mock_creds = MagicMock()
        mock_creds.valid = True

        mock_creds_cls = MagicMock()
        mock_creds_cls.from_authorized_user_file.return_value = mock_creds

        mock_build = MagicMock(return_value="gmail_service")

        monkeypatch.setattr(mod, "_token_path", lambda: token_file)
        monkeypatch.setattr(mod, "_credentials_path", lambda: creds_file)
        monkeypatch.setattr("haiku_skills_gmail.Credentials", mock_creds_cls)
        monkeypatch.setattr("haiku_skills_gmail.build", mock_build)

        result = mod._get_service()
        assert result == "gmail_service"
        assert mod._service == "gmail_service"
        mock_creds_cls.from_authorized_user_file.assert_called_once_with(
            str(token_file), mod.SCOPES
        )
        mock_build.assert_called_once_with("gmail", "v1", credentials=mock_creds)

    def test_get_service_token_refresh(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        import haiku_skills_gmail as mod

        token_file = tmp_path / "token.json"
        token_file.write_text("{}")
        creds_file = tmp_path / "credentials.json"
        creds_file.write_text("{}")

        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "refresh-token"
        mock_creds.to_json.return_value = '{"token": "refreshed"}'

        mock_creds_cls = MagicMock()
        mock_creds_cls.from_authorized_user_file.return_value = mock_creds

        mock_build = MagicMock(return_value="gmail_service")
        mock_request = MagicMock()
        mock_request_cls = MagicMock(return_value=mock_request)

        monkeypatch.setattr(mod, "_token_path", lambda: token_file)
        monkeypatch.setattr(mod, "_credentials_path", lambda: creds_file)
        monkeypatch.setattr("haiku_skills_gmail.Credentials", mock_creds_cls)
        monkeypatch.setattr("haiku_skills_gmail.build", mock_build)
        monkeypatch.setattr("haiku_skills_gmail.Request", mock_request_cls)

        result = mod._get_service()
        assert result == "gmail_service"
        mock_creds.refresh.assert_called_once_with(mock_request)
        assert token_file.read_text() == '{"token": "refreshed"}'

    def test_get_service_browser_flow(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        import haiku_skills_gmail as mod

        token_file = tmp_path / "token.json"
        creds_file = tmp_path / "credentials.json"
        creds_file.write_text("{}")

        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_creds.to_json.return_value = '{"token": "new"}'

        mock_flow = MagicMock()
        mock_flow.run_local_server.return_value = mock_creds
        mock_flow_cls = MagicMock()
        mock_flow_cls.from_client_secrets_file.return_value = mock_flow

        mock_build = MagicMock(return_value="gmail_service")

        monkeypatch.setattr(mod, "_token_path", lambda: token_file)
        monkeypatch.setattr(mod, "_credentials_path", lambda: creds_file)
        monkeypatch.setattr("haiku_skills_gmail.InstalledAppFlow", mock_flow_cls)
        monkeypatch.setattr("haiku_skills_gmail.build", mock_build)

        result = mod._get_service()
        assert result == "gmail_service"
        mock_flow_cls.from_client_secrets_file.assert_called_once_with(
            str(creds_file), mod.SCOPES
        )
        mock_flow.run_local_server.assert_called_once_with(port=0)
        assert token_file.read_text() == '{"token": "new"}'

    # -- Helpers --

    def test_get_header(self):
        from haiku_skills_gmail import _get_header

        headers = [
            {"name": "Subject", "value": "Hello"},
            {"name": "From", "value": "alice@example.com"},
        ]
        assert _get_header(headers, "Subject") == "Hello"
        assert _get_header(headers, "From") == "alice@example.com"

    def test_get_header_missing(self):
        from haiku_skills_gmail import _get_header

        assert _get_header([], "Subject") == ""
        assert _get_header([{"name": "From", "value": "x"}], "Subject") == ""

    def test_parse_email_body_plain(self):
        from haiku_skills_gmail import _parse_email_body

        payload = {
            "mimeType": "text/plain",
            "body": {"data": "SGVsbG8gV29ybGQ="},  # "Hello World"
        }
        assert _parse_email_body(payload) == "Hello World"

    def test_parse_email_body_multipart(self):
        from haiku_skills_gmail import _parse_email_body

        payload = {
            "mimeType": "multipart/alternative",
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"data": "UGxhaW4gdGV4dA=="},  # "Plain text"
                },
                {
                    "mimeType": "text/html",
                    "body": {"data": "PFBIVE1MIGJvZHk="},
                },
            ],
        }
        assert _parse_email_body(payload) == "Plain text"

    def test_parse_email_body_multipart_no_plain(self):
        from haiku_skills_gmail import _parse_email_body

        payload = {
            "mimeType": "multipart/alternative",
            "parts": [
                {
                    "mimeType": "text/html",
                    "body": {"data": "PFBIVE1MIGJvZHk="},
                },
            ],
        }
        assert _parse_email_body(payload) == ""

    def test_parse_email_body_plain_empty_data(self):
        from haiku_skills_gmail import _parse_email_body

        payload = {"mimeType": "text/plain", "body": {"data": ""}}
        assert _parse_email_body(payload) == ""

    def test_parse_email_body_nested_multipart(self):
        from haiku_skills_gmail import _parse_email_body

        payload = {
            "mimeType": "multipart/mixed",
            "parts": [
                {
                    "mimeType": "multipart/alternative",
                    "parts": [
                        {
                            "mimeType": "text/plain",
                            "body": {"data": "TmVzdGVk"},  # "Nested"
                        },
                    ],
                },
            ],
        }
        assert _parse_email_body(payload) == "Nested"

    def test_build_message(self):
        from haiku_skills_gmail import _build_message

        result = _build_message(
            to="bob@example.com",
            subject="Test",
            body="Hello Bob",
        )
        assert "raw" in result
        import base64

        decoded = base64.urlsafe_b64decode(result["raw"]).decode()
        assert "To: bob@example.com" in decoded
        assert "Subject: Test" in decoded
        assert "Hello Bob" in decoded

    def test_build_message_with_cc_bcc(self):
        from haiku_skills_gmail import _build_message

        result = _build_message(
            to="bob@example.com",
            subject="Test",
            body="Hello",
            cc="carol@example.com",
            bcc="dave@example.com",
        )
        import base64

        decoded = base64.urlsafe_b64decode(result["raw"]).decode()
        assert "Cc: carol@example.com" in decoded
        assert "Bcc: dave@example.com" in decoded

    def test_build_message_with_headers(self):
        from haiku_skills_gmail import _build_message

        result = _build_message(
            to="bob@example.com",
            subject="Re: Test",
            body="Reply body",
            in_reply_to="<msg123@example.com>",
            references="<msg123@example.com>",
        )
        import base64

        decoded = base64.urlsafe_b64decode(result["raw"]).decode()
        assert "In-Reply-To: <msg123@example.com>" in decoded
        assert "References: <msg123@example.com>" in decoded

    def test_format_email_summary(self):
        from haiku_skills_gmail import _format_email_summary

        msg = {
            "id": "msg1",
            "threadId": "thread1",
            "snippet": "Hey there...",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Meeting"},
                    {"name": "From", "value": "alice@example.com"},
                    {"name": "Date", "value": "Mon, 10 Mar 2026"},
                ],
            },
        }
        result = _format_email_summary(msg)
        assert "msg1" in result
        assert "Meeting" in result
        assert "alice@example.com" in result
        assert "Mon, 10 Mar 2026" in result
        assert "Hey there..." in result

    # -- Mock service helper --

    def _mock_service(self) -> MagicMock:
        service = MagicMock()
        return service

    def _sample_message(
        self,
        msg_id: str = "msg1",
        thread_id: str = "thread1",
        subject: str = "Test Subject",
        sender: str = "alice@example.com",
        snippet: str = "Preview text...",
        body_data: str = "SGVsbG8gV29ybGQ=",  # "Hello World"
    ) -> dict:
        return {
            "id": msg_id,
            "threadId": thread_id,
            "snippet": snippet,
            "payload": {
                "headers": [
                    {"name": "Subject", "value": subject},
                    {"name": "From", "value": sender},
                    {"name": "Date", "value": "Mon, 10 Mar 2026"},
                    {"name": "Message-ID", "value": f"<{msg_id}@example.com>"},
                ],
                "mimeType": "text/plain",
                "body": {"data": body_data},
            },
        }

    # -- Search --

    def test_search_emails(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_gmail as mod
        from haiku_skills_gmail import EmailState, search_emails

        service = self._mock_service()
        msg = self._sample_message()
        service.users().messages().list.return_value.execute.return_value = {
            "messages": [{"id": "msg1", "threadId": "thread1"}],
            "resultSizeEstimate": 1,
        }
        service.users().messages().get.return_value.execute.return_value = msg
        monkeypatch.setattr(mod, "_get_service", lambda: service)

        state = EmailState()
        ctx = _make_ctx(state)
        result = search_emails(ctx, "from:alice")

        assert "msg1" in result
        assert "Test Subject" in result
        assert "alice@example.com" in result
        assert "from:alice" in state.searches
        assert len(state.searches["from:alice"]) == 1
        assert state.searches["from:alice"][0].message_id == "msg1"

    def test_search_emails_no_results(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_gmail as mod
        from haiku_skills_gmail import search_emails

        service = self._mock_service()
        service.users().messages().list.return_value.execute.return_value = {
            "resultSizeEstimate": 0,
        }
        monkeypatch.setattr(mod, "_get_service", lambda: service)

        ctx = _make_ctx()
        result = search_emails(ctx, "nonexistent")
        assert "No emails found" in result

    def test_search_emails_message_fetch_error(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_gmail as mod
        from haiku_skills_gmail import search_emails

        service = self._mock_service()
        service.users().messages().list.return_value.execute.return_value = {
            "messages": [{"id": "msg1", "threadId": "thread1"}],
            "resultSizeEstimate": 1,
        }
        service.users().messages().get.return_value.execute.side_effect = RuntimeError(
            "fetch failed"
        )
        monkeypatch.setattr(mod, "_get_service", lambda: service)

        ctx = _make_ctx()
        result = search_emails(ctx, "test")
        assert "No emails found" in result

    def test_search_emails_error(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_gmail as mod
        from haiku_skills_gmail import search_emails

        service = self._mock_service()
        service.users().messages().list.return_value.execute.side_effect = RuntimeError(
            "API error"
        )
        monkeypatch.setattr(mod, "_get_service", lambda: service)

        ctx = _make_ctx()
        result = search_emails(ctx, "test")
        assert result.startswith("Error:")
        assert "API error" in result

    # -- Read --

    def test_read_email(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_gmail as mod
        from haiku_skills_gmail import EmailState, read_email

        service = self._mock_service()
        msg = self._sample_message()
        service.users().messages().get.return_value.execute.return_value = msg
        monkeypatch.setattr(mod, "_get_service", lambda: service)

        state = EmailState()
        ctx = _make_ctx(state)
        result = read_email(ctx, "msg1")

        assert "Test Subject" in result
        assert "alice@example.com" in result
        assert "Hello World" in result
        assert state.read_emails["msg1"] == "Test Subject"

    def test_read_email_error(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_gmail as mod
        from haiku_skills_gmail import read_email

        service = self._mock_service()
        service.users().messages().get.return_value.execute.side_effect = RuntimeError(
            "not found"
        )
        monkeypatch.setattr(mod, "_get_service", lambda: service)

        ctx = _make_ctx()
        result = read_email(ctx, "bad_id")
        assert result.startswith("Error:")
        assert "not found" in result
