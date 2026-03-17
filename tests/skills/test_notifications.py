"""Tests for the notifications skill package."""

import io
import runpy
from unittest.mock import MagicMock

import pytest

from haiku.skills.models import SkillSource

from .conftest import SKILLS_ROOT, make_ctx


class TestNotifications:
    def test_create_skill(self):
        from haiku_skills_notifications import create_skill

        skill = create_skill()
        assert skill.metadata.name == "notifications"
        assert (
            skill.metadata.description
            == "Send and receive push notifications via ntfy.sh."
        )
        assert skill.source == SkillSource.ENTRYPOINT
        assert skill.path is not None
        assert skill.instructions is not None
        assert skill.state_type is not None
        assert skill.state_namespace == "notifications"
        assert len(skill.tools) == 2

    def test_send_notification(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_notifications.scripts.send_notification as mod
        import httpx

        def mock_post(url, content, headers):
            assert url == "https://ntfy.sh/test-topic"
            assert content == "Hello world"
            resp = MagicMock(spec=httpx.Response)
            resp.raise_for_status = MagicMock()
            return resp

        monkeypatch.setattr(mod.httpx, "post", mock_post)
        monkeypatch.delenv("NTFY_TOKEN", raising=False)

        from haiku_skills_notifications.scripts.send_notification import main

        result = main("test-topic", "Hello world")
        assert result == "Notification sent to topic 'test-topic'."

    def test_send_notification_with_title_and_priority(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        import haiku_skills_notifications.scripts.send_notification as mod
        import httpx

        captured_headers: dict[str, str] = {}

        def mock_post(url, content, headers):
            captured_headers.update(headers)
            resp = MagicMock(spec=httpx.Response)
            resp.raise_for_status = MagicMock()
            return resp

        monkeypatch.setattr(mod.httpx, "post", mock_post)
        monkeypatch.delenv("NTFY_TOKEN", raising=False)

        from haiku_skills_notifications.scripts.send_notification import main

        result = main("test-topic", "Urgent!", title="Alert", priority="high")
        assert result == "Notification sent to topic 'test-topic'."
        assert captured_headers["X-Title"] == "Alert"
        assert captured_headers["X-Priority"] == "high"

    def test_send_notification_error(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_notifications.scripts.send_notification as mod
        import httpx

        def mock_post(url, content, headers):
            raise httpx.HTTPError("connection failed")

        monkeypatch.setattr(mod.httpx, "post", mock_post)
        monkeypatch.delenv("NTFY_TOKEN", raising=False)

        from haiku_skills_notifications.scripts.send_notification import main

        result = main("test-topic", "Hello")
        assert result.startswith("Error:")
        assert "connection failed" in result

    def test_send_notification_custom_server(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_notifications.scripts.send_notification as mod
        import httpx

        captured_url = ""

        def mock_post(url, content, headers):
            nonlocal captured_url
            captured_url = url
            resp = MagicMock(spec=httpx.Response)
            resp.raise_for_status = MagicMock()
            return resp

        monkeypatch.setattr(mod.httpx, "post", mock_post)
        monkeypatch.delenv("NTFY_TOKEN", raising=False)

        from haiku_skills_notifications.scripts.send_notification import main

        main("test-topic", "Hello", server="http://localhost:2586")
        assert captured_url == "http://localhost:2586/test-topic"

    def test_send_notification_server_from_env(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_notifications.scripts.send_notification as mod
        import httpx

        captured_url = ""

        def mock_post(url, content, headers):
            nonlocal captured_url
            captured_url = url
            resp = MagicMock(spec=httpx.Response)
            resp.raise_for_status = MagicMock()
            return resp

        monkeypatch.setattr(mod.httpx, "post", mock_post)
        monkeypatch.setenv("NTFY_SERVER", "http://myserver:8080")
        monkeypatch.delenv("NTFY_TOKEN", raising=False)

        from haiku_skills_notifications.scripts.send_notification import main

        main("test-topic", "Hello")
        assert captured_url == "http://myserver:8080/test-topic"

    def test_send_notification_auth_token(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_notifications.scripts.send_notification as mod
        import httpx

        captured_headers: dict[str, str] = {}

        def mock_post(url, content, headers):
            captured_headers.update(headers)
            resp = MagicMock(spec=httpx.Response)
            resp.raise_for_status = MagicMock()
            return resp

        monkeypatch.setattr(mod.httpx, "post", mock_post)
        monkeypatch.setenv("NTFY_TOKEN", "tk_secret123")

        from haiku_skills_notifications.scripts.send_notification import main

        main("test-topic", "Hello")
        assert captured_headers["Authorization"] == "Bearer tk_secret123"

    def test_send_notification_tool_with_state(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_notifications.scripts.send_notification as mod
        import httpx

        def mock_post(url, content, headers):
            resp = MagicMock(spec=httpx.Response)
            resp.raise_for_status = MagicMock()
            return resp

        monkeypatch.setattr(mod.httpx, "post", mock_post)
        monkeypatch.delenv("NTFY_TOKEN", raising=False)

        from haiku_skills_notifications import (
            NotificationState,
            send_notification,
        )

        state = NotificationState()
        ctx = make_ctx(state)
        result = send_notification(ctx, "test-topic", "Hello", title="Hi")
        assert result == "Notification sent to topic 'test-topic'."
        assert len(state.sent) == 1
        assert state.sent[0].topic == "test-topic"
        assert state.sent[0].message == "Hello"
        assert state.sent[0].title == "Hi"
        assert state.sent[0].priority == 3

    def test_send_notification_tool_error_no_state(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        import haiku_skills_notifications.scripts.send_notification as mod
        import httpx

        def mock_post(url, content, headers):
            raise httpx.HTTPError("fail")

        monkeypatch.setattr(mod.httpx, "post", mock_post)
        monkeypatch.delenv("NTFY_TOKEN", raising=False)

        from haiku_skills_notifications import (
            NotificationState,
            send_notification,
        )

        state = NotificationState()
        ctx = make_ctx(state)
        result = send_notification(ctx, "test-topic", "Hello")
        assert result.startswith("Error:")
        assert len(state.sent) == 0

    def test_send_notification_main_entry(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_notifications.scripts.send_notification as mod
        import httpx

        def mock_post(url, content, headers):
            resp = MagicMock(spec=httpx.Response)
            resp.raise_for_status = MagicMock()
            return resp

        monkeypatch.setattr(mod.httpx, "post", mock_post)
        monkeypatch.delenv("NTFY_TOKEN", raising=False)

        monkeypatch.setattr("sys.argv", ["send_notification.py", "test-topic", "Hello"])
        captured = io.StringIO()
        monkeypatch.setattr("sys.stdout", captured)

        script = (
            SKILLS_ROOT
            / "notifications"
            / "haiku_skills_notifications"
            / "scripts"
            / "send_notification.py"
        )
        runpy.run_path(str(script), run_name="__main__")

        assert "Notification sent" in captured.getvalue()

    def test_read_notifications(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_notifications.scripts.read_notifications as mod
        import httpx

        lines = "\n".join(
            [
                '{"event":"open","topic":"test-topic"}',
                '{"event":"message","id":"abc1","topic":"test-topic","message":"Hello","title":"","priority":3,"time":1000}',
                "",
                '{"event":"message","id":"abc2","topic":"test-topic","message":"World","title":"Alert","priority":5,"time":1001}',
            ]
        )

        def mock_get(url, params, headers):
            assert "test-topic/json" in url
            resp = MagicMock(spec=httpx.Response)
            resp.raise_for_status = MagicMock()
            resp.text = lines
            return resp

        monkeypatch.setattr(mod.httpx, "get", mock_get)
        monkeypatch.delenv("NTFY_TOKEN", raising=False)

        from haiku_skills_notifications.scripts.read_notifications import main

        result = main("test-topic", since="all")
        assert "Hello" in result
        assert "World" in result
        assert "**Alert**" in result
        assert "(priority: 5)" in result

    def test_read_notifications_no_messages(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_notifications.scripts.read_notifications as mod
        import httpx

        def mock_get(url, params, headers):
            resp = MagicMock(spec=httpx.Response)
            resp.raise_for_status = MagicMock()
            resp.text = '{"event":"open","topic":"test-topic"}'
            return resp

        monkeypatch.setattr(mod.httpx, "get", mock_get)
        monkeypatch.delenv("NTFY_TOKEN", raising=False)

        from haiku_skills_notifications.scripts.read_notifications import main

        result = main("test-topic")
        assert result == "No messages on topic 'test-topic'."

    def test_read_notifications_error(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_notifications.scripts.read_notifications as mod
        import httpx

        def mock_get(url, params, headers):
            raise httpx.HTTPError("connection failed")

        monkeypatch.setattr(mod.httpx, "get", mock_get)
        monkeypatch.delenv("NTFY_TOKEN", raising=False)

        from haiku_skills_notifications.scripts.read_notifications import main

        result = main("test-topic")
        assert result.startswith("Error:")
        assert "connection failed" in result

    def test_read_notifications_custom_server(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_notifications.scripts.read_notifications as mod
        import httpx

        captured_url = ""

        def mock_get(url, params, headers):
            nonlocal captured_url
            captured_url = url
            resp = MagicMock(spec=httpx.Response)
            resp.raise_for_status = MagicMock()
            resp.text = ""
            return resp

        monkeypatch.setattr(mod.httpx, "get", mock_get)
        monkeypatch.delenv("NTFY_TOKEN", raising=False)

        from haiku_skills_notifications.scripts.read_notifications import main

        main("test-topic", server="http://localhost:2586")
        assert captured_url == "http://localhost:2586/test-topic/json"

    def test_read_notifications_auth_token(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_notifications.scripts.read_notifications as mod
        import httpx

        captured_headers: dict[str, str] = {}

        def mock_get(url, params, headers):
            captured_headers.update(headers)
            resp = MagicMock(spec=httpx.Response)
            resp.raise_for_status = MagicMock()
            resp.text = ""
            return resp

        monkeypatch.setattr(mod.httpx, "get", mock_get)
        monkeypatch.setenv("NTFY_TOKEN", "tk_secret123")

        from haiku_skills_notifications.scripts.read_notifications import main

        main("test-topic")
        assert captured_headers["Authorization"] == "Bearer tk_secret123"

    def test_read_notifications_tool_with_state(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_notifications.scripts.read_notifications as mod
        import httpx

        lines = "\n".join(
            [
                '{"event":"message","id":"msg1","topic":"test-topic","message":"Hello","title":"Greet","priority":5,"time":1000}',
            ]
        )

        def mock_get(url, params, headers):
            resp = MagicMock(spec=httpx.Response)
            resp.raise_for_status = MagicMock()
            resp.text = lines
            return resp

        monkeypatch.setattr(mod.httpx, "get", mock_get)
        monkeypatch.delenv("NTFY_TOKEN", raising=False)

        from haiku_skills_notifications import (
            NotificationState,
            read_notifications,
        )

        state = NotificationState()
        ctx = make_ctx(state)
        result = read_notifications(ctx, "test-topic", since="all")
        assert "Hello" in result
        assert "(priority: 5)" in result
        assert len(state.received) == 1
        assert state.received[0].id == "msg1"
        assert state.received[0].topic == "test-topic"
        assert state.received[0].message == "Hello"
        assert state.received[0].title == "Greet"
        assert state.received[0].priority == 5

    def test_read_notifications_tool_no_messages_state(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        import haiku_skills_notifications.scripts.read_notifications as mod
        import httpx

        def mock_get(url, params, headers):
            resp = MagicMock(spec=httpx.Response)
            resp.raise_for_status = MagicMock()
            resp.text = ""
            return resp

        monkeypatch.setattr(mod.httpx, "get", mock_get)
        monkeypatch.delenv("NTFY_TOKEN", raising=False)

        from haiku_skills_notifications import (
            NotificationState,
            read_notifications,
        )

        state = NotificationState()
        ctx = make_ctx(state)
        result = read_notifications(ctx, "test-topic")
        assert "No messages" in result
        assert len(state.received) == 0

    def test_read_notifications_tool_error_no_state(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        import haiku_skills_notifications.scripts.read_notifications as mod
        import httpx

        def mock_get(url, params, headers):
            raise httpx.HTTPError("fail")

        monkeypatch.setattr(mod.httpx, "get", mock_get)
        monkeypatch.delenv("NTFY_TOKEN", raising=False)

        from haiku_skills_notifications import (
            NotificationState,
            read_notifications,
        )

        state = NotificationState()
        ctx = make_ctx(state)
        result = read_notifications(ctx, "test-topic")
        assert result.startswith("Error:")
        assert len(state.received) == 0

    def test_read_notifications_main_entry(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_notifications.scripts.read_notifications as mod
        import httpx

        def mock_get(url, params, headers):
            resp = MagicMock(spec=httpx.Response)
            resp.raise_for_status = MagicMock()
            resp.text = ""
            return resp

        monkeypatch.setattr(mod.httpx, "get", mock_get)
        monkeypatch.delenv("NTFY_TOKEN", raising=False)

        monkeypatch.setattr("sys.argv", ["read_notifications.py", "test-topic"])
        captured = io.StringIO()
        monkeypatch.setattr("sys.stdout", captured)

        script = (
            SKILLS_ROOT
            / "notifications"
            / "haiku_skills_notifications"
            / "scripts"
            / "read_notifications.py"
        )
        runpy.run_path(str(script), run_name="__main__")

        assert "No messages" in captured.getvalue()

    def test_parse_priority(self):
        from haiku_skills_notifications import _parse_priority

        assert _parse_priority("min") == 1
        assert _parse_priority("low") == 2
        assert _parse_priority("default") == 3
        assert _parse_priority("high") == 4
        assert _parse_priority("max") == 5
        assert _parse_priority("3") == 3
        assert _parse_priority("5") == 5
        assert _parse_priority("unknown") == 3

    def test_send_notification_tool_priority_stored_as_int(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        import haiku_skills_notifications.scripts.send_notification as mod
        import httpx

        def mock_post(url, content, headers):
            resp = MagicMock(spec=httpx.Response)
            resp.raise_for_status = MagicMock()
            return resp

        monkeypatch.setattr(mod.httpx, "post", mock_post)
        monkeypatch.delenv("NTFY_TOKEN", raising=False)

        from haiku_skills_notifications import (
            NotificationState,
            send_notification,
        )

        state = NotificationState()
        ctx = make_ctx(state)
        send_notification(ctx, "test-topic", "Hello", priority="high")
        assert state.sent[0].priority == 4

    def test_format_messages(self):
        from haiku_skills_notifications.scripts.read_notifications import (
            format_messages,
        )

        messages = [
            {"message": "Hello", "priority": 3},
            {"message": "Urgent", "title": "Alert", "priority": 5},
        ]
        result = format_messages(messages)
        assert "Hello" in result
        assert "**Alert**" in result
        assert "(priority: 5)" in result
        assert "(priority: 3)" not in result

    def test_resolve_server(self, monkeypatch: pytest.MonkeyPatch):
        from haiku_skills_notifications.scripts.ntfy import resolve_server

        monkeypatch.delenv("NTFY_SERVER", raising=False)
        assert resolve_server() == "https://ntfy.sh"
        assert resolve_server("http://custom:8080") == "http://custom:8080"
        monkeypatch.setenv("NTFY_SERVER", "http://env-server:9090")
        assert resolve_server() == "http://env-server:9090"
        assert resolve_server("http://explicit:8080") == "http://explicit:8080"

    def test_auth_headers(self, monkeypatch: pytest.MonkeyPatch):
        from haiku_skills_notifications.scripts.ntfy import auth_headers

        monkeypatch.delenv("NTFY_TOKEN", raising=False)
        assert auth_headers() == {}
        monkeypatch.setenv("NTFY_TOKEN", "tk_test")
        assert auth_headers() == {"Authorization": "Bearer tk_test"}
