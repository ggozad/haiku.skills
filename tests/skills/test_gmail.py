"""Tests for the gmail skill package."""

import base64
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from .conftest import make_ctx


class TestGmail:
    @pytest.fixture(autouse=True)
    def _reset_globals(self, monkeypatch: pytest.MonkeyPatch):
        """Reset module-level singleton state between tests."""
        import haiku_skills_gmail._auth as auth_mod

        monkeypatch.setattr(auth_mod, "_service", None)

    def test_create_skill(self):
        from haiku_skills_gmail import create_skill

        skill = create_skill()
        assert skill.metadata.name == "gmail"
        assert (
            skill.metadata.description == "Search, read, send, and manage Gmail emails."
        )
        assert skill.instructions is not None
        assert skill.state_type is not None
        assert skill.state_namespace == "gmail"
        assert len(skill.tools) == 8

    # -- Config --

    def test_credentials_path_default(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("EMAIL_CREDENTIALS_PATH", raising=False)
        from haiku_skills_gmail._auth import _credentials_path

        result = _credentials_path()
        assert (
            result
            == Path.home() / ".config" / "haiku-skills-gmail" / "credentials.json"
        )

    def test_credentials_path_from_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("EMAIL_CREDENTIALS_PATH", "/tmp/my-creds.json")
        from haiku_skills_gmail._auth import _credentials_path

        assert _credentials_path() == Path("/tmp/my-creds.json")

    def test_token_path_default(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("EMAIL_TOKEN_PATH", raising=False)
        from haiku_skills_gmail._auth import _token_path

        result = _token_path()
        assert result == Path.home() / ".config" / "haiku-skills-gmail" / "token.json"

    def test_token_path_from_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("EMAIL_TOKEN_PATH", "/tmp/my-token.json")
        from haiku_skills_gmail._auth import _token_path

        assert _token_path() == Path("/tmp/my-token.json")

    # -- Auth --

    def test_get_service_cached(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_gmail._auth as auth_mod

        sentinel = MagicMock()
        monkeypatch.setattr(auth_mod, "_service", sentinel)

        result = auth_mod._get_service()
        assert result is sentinel

    def test_get_service_no_credentials_file(self, monkeypatch: pytest.MonkeyPatch):
        import haiku_skills_gmail._auth as auth_mod

        monkeypatch.setattr(
            auth_mod, "_credentials_path", lambda: Path("/nonexistent/creds.json")
        )

        with pytest.raises(FileNotFoundError, match="credentials.json"):
            auth_mod._get_service()

    def test_get_service_from_token(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        import haiku_skills_gmail._auth as auth_mod

        token_file = tmp_path / "token.json"
        token_file.write_text("{}")
        creds_file = tmp_path / "credentials.json"
        creds_file.write_text("{}")

        mock_creds = MagicMock()
        mock_creds.valid = True

        mock_creds_cls = MagicMock()
        mock_creds_cls.from_authorized_user_file.return_value = mock_creds

        mock_build = MagicMock(return_value="gmail_service")

        monkeypatch.setattr(auth_mod, "_token_path", lambda: token_file)
        monkeypatch.setattr(auth_mod, "_credentials_path", lambda: creds_file)
        monkeypatch.setattr("haiku_skills_gmail._auth.Credentials", mock_creds_cls)
        monkeypatch.setattr("haiku_skills_gmail._auth.build", mock_build)

        result = auth_mod._get_service()
        assert result == "gmail_service"
        assert auth_mod._service == "gmail_service"
        mock_creds_cls.from_authorized_user_file.assert_called_once_with(
            str(token_file), auth_mod.SCOPES
        )
        mock_build.assert_called_once_with("gmail", "v1", credentials=mock_creds)

    def test_get_service_token_refresh(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        import haiku_skills_gmail._auth as auth_mod

        token_file = tmp_path / "token.json"
        token_file.write_text("{}")
        creds_file = tmp_path / "credentials.json"
        creds_file.write_text("{}")

        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "refresh-token"
        mock_creds.to_json.return_value = '{"token": "refreshed"}'
        mock_creds.refresh.side_effect = lambda _req: setattr(mock_creds, "valid", True)

        mock_creds_cls = MagicMock()
        mock_creds_cls.from_authorized_user_file.return_value = mock_creds

        mock_build = MagicMock(return_value="gmail_service")
        mock_request = MagicMock()
        mock_request_cls = MagicMock(return_value=mock_request)

        monkeypatch.setattr(auth_mod, "_token_path", lambda: token_file)
        monkeypatch.setattr(auth_mod, "_credentials_path", lambda: creds_file)
        monkeypatch.setattr("haiku_skills_gmail._auth.Credentials", mock_creds_cls)
        monkeypatch.setattr("haiku_skills_gmail._auth.build", mock_build)
        monkeypatch.setattr("haiku_skills_gmail._auth.Request", mock_request_cls)

        result = auth_mod._get_service()
        assert result == "gmail_service"
        mock_creds.refresh.assert_called_once_with(mock_request)
        assert token_file.read_text() == '{"token": "refreshed"}'

    def test_get_service_token_refresh_failure_falls_back_to_browser(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        import haiku_skills_gmail._auth as auth_mod

        token_file = tmp_path / "token.json"
        token_file.write_text("{}")
        creds_file = tmp_path / "credentials.json"
        creds_file.write_text("{}")

        expired_creds = MagicMock()
        expired_creds.valid = False
        expired_creds.expired = True
        expired_creds.refresh_token = "refresh-token"
        expired_creds.refresh.side_effect = Exception("Token has been expired or revoked.")

        fresh_creds = MagicMock()
        fresh_creds.valid = True
        fresh_creds.to_json.return_value = '{"token": "new"}'

        mock_creds_cls = MagicMock()
        mock_creds_cls.from_authorized_user_file.return_value = expired_creds

        mock_flow = MagicMock()
        mock_flow.run_local_server.return_value = fresh_creds
        mock_flow_cls = MagicMock()
        mock_flow_cls.from_client_secrets_file.return_value = mock_flow

        mock_build = MagicMock(return_value="gmail_service")
        mock_request_cls = MagicMock()

        monkeypatch.setattr(auth_mod, "_token_path", lambda: token_file)
        monkeypatch.setattr(auth_mod, "_credentials_path", lambda: creds_file)
        monkeypatch.setattr("haiku_skills_gmail._auth.Credentials", mock_creds_cls)
        monkeypatch.setattr("haiku_skills_gmail._auth.build", mock_build)
        monkeypatch.setattr("haiku_skills_gmail._auth.Request", mock_request_cls)
        monkeypatch.setattr("haiku_skills_gmail._auth.InstalledAppFlow", mock_flow_cls)

        result = auth_mod._get_service()
        assert result == "gmail_service"
        expired_creds.refresh.assert_called_once()
        mock_flow.run_local_server.assert_called_once_with(port=0)
        assert token_file.read_text() == '{"token": "new"}'
        mock_build.assert_called_once_with("gmail", "v1", credentials=fresh_creds)

    def test_get_service_browser_flow(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        import haiku_skills_gmail._auth as auth_mod

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

        monkeypatch.setattr(auth_mod, "_token_path", lambda: token_file)
        monkeypatch.setattr(auth_mod, "_credentials_path", lambda: creds_file)
        monkeypatch.setattr("haiku_skills_gmail._auth.InstalledAppFlow", mock_flow_cls)
        monkeypatch.setattr("haiku_skills_gmail._auth.build", mock_build)

        result = auth_mod._get_service()
        assert result == "gmail_service"
        mock_flow_cls.from_client_secrets_file.assert_called_once_with(
            str(creds_file), auth_mod.SCOPES
        )
        mock_flow.run_local_server.assert_called_once_with(port=0)
        assert token_file.read_text() == '{"token": "new"}'

    # -- Helpers --

    def test_get_header(self):
        from haiku_skills_gmail._helpers import _get_header

        headers = [
            {"name": "Subject", "value": "Hello"},
            {"name": "From", "value": "alice@example.com"},
        ]
        assert _get_header(headers, "Subject") == "Hello"
        assert _get_header(headers, "From") == "alice@example.com"

    def test_get_header_missing(self):
        from haiku_skills_gmail._helpers import _get_header

        assert _get_header([], "Subject") == ""
        assert _get_header([{"name": "From", "value": "x"}], "Subject") == ""

    def test_parse_email_body_plain(self):
        from haiku_skills_gmail._helpers import _parse_email_body

        payload = {
            "mimeType": "text/plain",
            "body": {"data": "SGVsbG8gV29ybGQ="},  # "Hello World"
        }
        assert _parse_email_body(payload) == "Hello World"

    def test_parse_email_body_multipart(self):
        from haiku_skills_gmail._helpers import _parse_email_body

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
        from haiku_skills_gmail._helpers import _parse_email_body

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
        from haiku_skills_gmail._helpers import _parse_email_body

        payload = {"mimeType": "text/plain", "body": {"data": ""}}
        assert _parse_email_body(payload) == ""

    def test_parse_email_body_nested_multipart(self):
        from haiku_skills_gmail._helpers import _parse_email_body

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
        from haiku_skills_gmail._helpers import _build_message

        result = _build_message(
            to="bob@example.com",
            subject="Test",
            body="Hello Bob",
        )
        assert "raw" in result

        decoded = base64.urlsafe_b64decode(result["raw"]).decode()
        assert "To: bob@example.com" in decoded
        assert "Subject: Test" in decoded
        assert "Hello Bob" in decoded

    def test_build_message_with_cc_bcc(self):
        from haiku_skills_gmail._helpers import _build_message

        result = _build_message(
            to="bob@example.com",
            subject="Test",
            body="Hello",
            cc="carol@example.com",
            bcc="dave@example.com",
        )

        decoded = base64.urlsafe_b64decode(result["raw"]).decode()
        assert "Cc: carol@example.com" in decoded
        assert "Bcc: dave@example.com" in decoded

    def test_build_message_with_headers(self):
        from haiku_skills_gmail._helpers import _build_message

        result = _build_message(
            to="bob@example.com",
            subject="Re: Test",
            body="Reply body",
            in_reply_to="<msg123@example.com>",
            references="<msg123@example.com>",
        )

        decoded = base64.urlsafe_b64decode(result["raw"]).decode()
        assert "In-Reply-To: <msg123@example.com>" in decoded
        assert "References: <msg123@example.com>" in decoded

    def test_format_email_summary(self):
        from haiku_skills_gmail._helpers import _format_email_summary

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

    def _patch_service(self, monkeypatch, service):
        """Patch _get_service across all script modules that import it."""
        import haiku_skills_gmail._create_draft as create_draft_mod
        import haiku_skills_gmail._list_drafts as list_drafts_mod
        import haiku_skills_gmail._list_labels as list_labels_mod
        import haiku_skills_gmail._modify_labels as modify_labels_mod
        import haiku_skills_gmail._read_email as read_email_mod
        import haiku_skills_gmail._reply_to_email as reply_to_email_mod
        import haiku_skills_gmail._search_emails as search_emails_mod
        import haiku_skills_gmail._send_email as send_email_mod

        for mod in (
            search_emails_mod,
            read_email_mod,
            send_email_mod,
            reply_to_email_mod,
            create_draft_mod,
            list_drafts_mod,
            modify_labels_mod,
            list_labels_mod,
        ):
            monkeypatch.setattr(mod, "_get_service", lambda: service)

    # -- Search --

    def test_search_emails(self, monkeypatch: pytest.MonkeyPatch):
        from haiku_skills_gmail import EmailState, search_emails

        service = self._mock_service()
        msg = self._sample_message()
        service.users().messages().list.return_value.execute.return_value = {
            "messages": [{"id": "msg1", "threadId": "thread1"}],
            "resultSizeEstimate": 1,
        }
        service.users().messages().get.return_value.execute.return_value = msg
        self._patch_service(monkeypatch, service)

        state = EmailState()
        ctx = make_ctx(state)
        result = search_emails(ctx, "from:alice")

        assert "msg1" in result
        assert "Test Subject" in result
        assert "alice@example.com" in result
        assert "from:alice" in state.searches
        assert len(state.searches["from:alice"]) == 1
        assert state.searches["from:alice"][0].message_id == "msg1"

    def test_search_emails_no_results(self, monkeypatch: pytest.MonkeyPatch):
        from haiku_skills_gmail import search_emails

        service = self._mock_service()
        service.users().messages().list.return_value.execute.return_value = {
            "resultSizeEstimate": 0,
        }
        self._patch_service(monkeypatch, service)

        ctx = make_ctx()
        result = search_emails(ctx, "nonexistent")
        assert "No emails found" in result

    def test_search_emails_message_fetch_error(self, monkeypatch: pytest.MonkeyPatch):
        from haiku_skills_gmail import search_emails

        service = self._mock_service()
        service.users().messages().list.return_value.execute.return_value = {
            "messages": [{"id": "msg1", "threadId": "thread1"}],
            "resultSizeEstimate": 1,
        }
        service.users().messages().get.return_value.execute.side_effect = RuntimeError(
            "fetch failed"
        )
        self._patch_service(monkeypatch, service)

        ctx = make_ctx()
        result = search_emails(ctx, "test")
        assert "No emails found" in result

    def test_search_emails_error(self, monkeypatch: pytest.MonkeyPatch):
        from haiku_skills_gmail import search_emails

        service = self._mock_service()
        service.users().messages().list.return_value.execute.side_effect = RuntimeError(
            "API error"
        )
        self._patch_service(monkeypatch, service)

        ctx = make_ctx()
        result = search_emails(ctx, "test")
        assert result.startswith("Error:")
        assert "API error" in result

    # -- Read --

    def test_read_email(self, monkeypatch: pytest.MonkeyPatch):
        from haiku_skills_gmail import EmailState, read_email

        service = self._mock_service()
        msg = self._sample_message()
        service.users().messages().get.return_value.execute.return_value = msg
        self._patch_service(monkeypatch, service)

        state = EmailState()
        ctx = make_ctx(state)
        result = read_email(ctx, "msg1")

        assert "Test Subject" in result
        assert "alice@example.com" in result
        assert "Hello World" in result
        assert state.read_emails["msg1"] == "Test Subject"

    def test_read_email_error(self, monkeypatch: pytest.MonkeyPatch):
        from haiku_skills_gmail import read_email

        service = self._mock_service()
        service.users().messages().get.return_value.execute.side_effect = RuntimeError(
            "not found"
        )
        self._patch_service(monkeypatch, service)

        ctx = make_ctx()
        result = read_email(ctx, "bad_id")
        assert result.startswith("Error:")
        assert "not found" in result

    # -- Send --

    def test_send_email(self, monkeypatch: pytest.MonkeyPatch):
        from haiku_skills_gmail import EmailState, send_email

        service = self._mock_service()
        service.users().messages().send.return_value.execute.return_value = {
            "id": "sent1",
            "threadId": "thread1",
        }
        self._patch_service(monkeypatch, service)

        state = EmailState()
        ctx = make_ctx(state)
        result = send_email(ctx, "bob@example.com", "Hello", "Hi Bob")

        assert "sent1" in result
        service.users().messages().send.assert_called_once()
        call_kwargs = service.users().messages().send.call_args.kwargs
        assert call_kwargs["userId"] == "me"
        assert "raw" in call_kwargs["body"]
        assert len(state.sent_emails) == 1
        assert state.sent_emails[0].message_id == "sent1"
        assert state.sent_emails[0].to == "bob@example.com"
        assert state.sent_emails[0].subject == "Hello"

    def test_send_email_with_cc_bcc(self, monkeypatch: pytest.MonkeyPatch):
        from haiku_skills_gmail import send_email

        service = self._mock_service()
        service.users().messages().send.return_value.execute.return_value = {
            "id": "sent2",
            "threadId": "thread2",
        }
        self._patch_service(monkeypatch, service)

        ctx = make_ctx()
        result = send_email(
            ctx,
            "bob@example.com",
            "Hello",
            "Hi Bob",
            cc="carol@example.com",
            bcc="dave@example.com",
        )
        assert "sent2" in result

        call_kwargs = service.users().messages().send.call_args.kwargs
        decoded = base64.urlsafe_b64decode(call_kwargs["body"]["raw"]).decode()
        assert "Cc: carol@example.com" in decoded
        assert "Bcc: dave@example.com" in decoded

    def test_send_email_error(self, monkeypatch: pytest.MonkeyPatch):
        from haiku_skills_gmail import send_email

        service = self._mock_service()
        service.users().messages().send.return_value.execute.side_effect = RuntimeError(
            "send failed"
        )
        self._patch_service(monkeypatch, service)

        ctx = make_ctx()
        result = send_email(ctx, "bob@example.com", "Hello", "Hi")
        assert result.startswith("Error:")
        assert "send failed" in result

    # -- Reply --

    def test_reply_to_email(self, monkeypatch: pytest.MonkeyPatch):
        from haiku_skills_gmail import EmailState, reply_to_email

        service = self._mock_service()
        original = self._sample_message(
            msg_id="orig1",
            thread_id="thread1",
            subject="Original Subject",
            sender="alice@example.com",
        )
        service.users().messages().get.return_value.execute.return_value = original
        service.users().messages().send.return_value.execute.return_value = {
            "id": "reply1",
            "threadId": "thread1",
        }
        self._patch_service(monkeypatch, service)

        state = EmailState()
        ctx = make_ctx(state)
        result = reply_to_email(ctx, "orig1", "Thanks!")

        assert "reply1" in result
        call_kwargs = service.users().messages().send.call_args.kwargs
        assert call_kwargs["body"]["threadId"] == "thread1"

        decoded = base64.urlsafe_b64decode(call_kwargs["body"]["raw"]).decode()
        assert "In-Reply-To: <orig1@example.com>" in decoded
        assert "Subject: Re: Original Subject" in decoded
        assert len(state.sent_emails) == 1
        assert state.sent_emails[0].message_id == "reply1"

    def test_reply_to_email_already_re(self, monkeypatch: pytest.MonkeyPatch):
        from haiku_skills_gmail import reply_to_email

        service = self._mock_service()
        original = self._sample_message(
            msg_id="orig1",
            thread_id="thread1",
            subject="Re: Original Subject",
        )
        service.users().messages().get.return_value.execute.return_value = original
        service.users().messages().send.return_value.execute.return_value = {
            "id": "reply1",
            "threadId": "thread1",
        }
        self._patch_service(monkeypatch, service)

        ctx = make_ctx()
        reply_to_email(ctx, "orig1", "Thanks!")

        call_kwargs = service.users().messages().send.call_args.kwargs
        decoded = base64.urlsafe_b64decode(call_kwargs["body"]["raw"]).decode()
        assert "Subject: Re: Original Subject" in decoded
        assert "Subject: Re: Re:" not in decoded

    def test_reply_to_email_reply_all(self, monkeypatch: pytest.MonkeyPatch):
        from haiku_skills_gmail import reply_to_email

        service = self._mock_service()
        original = {
            **self._sample_message(msg_id="orig1", thread_id="thread1"),
        }
        original["payload"]["headers"].append(
            {"name": "To", "value": "me@example.com, other@example.com"}
        )
        original["payload"]["headers"].append({"name": "Cc", "value": "cc@example.com"})
        service.users().messages().get.return_value.execute.return_value = original
        service.users().getProfile.return_value.execute.return_value = {
            "emailAddress": "me@example.com",
        }
        service.users().messages().send.return_value.execute.return_value = {
            "id": "reply1",
            "threadId": "thread1",
        }
        self._patch_service(monkeypatch, service)

        ctx = make_ctx()
        reply_to_email(ctx, "orig1", "Thanks!", reply_all=True)

        call_kwargs = service.users().messages().send.call_args.kwargs
        decoded = base64.urlsafe_b64decode(call_kwargs["body"]["raw"]).decode()
        assert "To: alice@example.com" in decoded
        assert "Cc: other@example.com, cc@example.com" in decoded
        assert "me@example.com" not in decoded

    def test_reply_to_email_error_send(self, monkeypatch: pytest.MonkeyPatch):
        from haiku_skills_gmail import reply_to_email

        service = self._mock_service()
        original = self._sample_message(msg_id="orig1", thread_id="thread1")
        service.users().messages().get.return_value.execute.return_value = original
        service.users().messages().send.return_value.execute.side_effect = RuntimeError(
            "send failed"
        )
        self._patch_service(monkeypatch, service)

        ctx = make_ctx()
        result = reply_to_email(ctx, "orig1", "Hello")
        assert result.startswith("Error:")
        assert "send failed" in result

    def test_reply_to_email_error_fetch(self, monkeypatch: pytest.MonkeyPatch):
        from haiku_skills_gmail import reply_to_email

        service = self._mock_service()
        service.users().messages().get.return_value.execute.side_effect = RuntimeError(
            "not found"
        )
        self._patch_service(monkeypatch, service)

        ctx = make_ctx()
        result = reply_to_email(ctx, "bad_id", "Hello")
        assert result.startswith("Error:")
        assert "not found" in result

    # -- Drafts --

    def test_create_draft(self, monkeypatch: pytest.MonkeyPatch):
        from haiku_skills_gmail import EmailState, create_draft

        service = self._mock_service()
        service.users().drafts().create.return_value.execute.return_value = {
            "id": "draft1",
            "message": {"id": "msg1", "threadId": "thread1"},
        }
        self._patch_service(monkeypatch, service)

        state = EmailState()
        ctx = make_ctx(state)
        result = create_draft(ctx, "bob@example.com", "Draft Subject", "Draft body")

        assert "draft1" in result
        service.users().drafts().create.assert_called_once()
        call_kwargs = service.users().drafts().create.call_args.kwargs
        assert call_kwargs["userId"] == "me"
        assert "raw" in call_kwargs["body"]["message"]
        assert len(state.drafts) == 1
        assert state.drafts[0].draft_id == "draft1"
        assert state.drafts[0].subject == "Draft Subject"
        assert state.drafts[0].to == "bob@example.com"

    def test_create_draft_error(self, monkeypatch: pytest.MonkeyPatch):
        from haiku_skills_gmail import create_draft

        service = self._mock_service()
        service.users().drafts().create.return_value.execute.side_effect = RuntimeError(
            "draft failed"
        )
        self._patch_service(monkeypatch, service)

        ctx = make_ctx()
        result = create_draft(ctx, "bob@example.com", "Subject", "Body")
        assert result.startswith("Error:")
        assert "draft failed" in result

    def test_list_drafts(self, monkeypatch: pytest.MonkeyPatch):
        from haiku_skills_gmail import list_drafts

        service = self._mock_service()
        service.users().drafts().list.return_value.execute.return_value = {
            "drafts": [
                {"id": "draft1", "message": {"id": "msg1"}},
                {"id": "draft2", "message": {"id": "msg2"}},
            ],
        }
        service.users().drafts().get.return_value.execute.side_effect = [
            {
                "id": "draft1",
                "message": {
                    "id": "msg1",
                    "payload": {
                        "headers": [
                            {"name": "Subject", "value": "Draft 1"},
                            {"name": "To", "value": "alice@example.com"},
                        ],
                    },
                },
            },
            {
                "id": "draft2",
                "message": {
                    "id": "msg2",
                    "payload": {
                        "headers": [
                            {"name": "Subject", "value": "Draft 2"},
                            {"name": "To", "value": "bob@example.com"},
                        ],
                    },
                },
            },
        ]
        self._patch_service(monkeypatch, service)

        ctx = make_ctx()
        result = list_drafts(ctx)
        assert "draft1" in result
        assert "Draft 1" in result
        assert "draft2" in result
        assert "Draft 2" in result

    def test_list_drafts_empty(self, monkeypatch: pytest.MonkeyPatch):
        from haiku_skills_gmail import list_drafts

        service = self._mock_service()
        service.users().drafts().list.return_value.execute.return_value = {}
        self._patch_service(monkeypatch, service)

        ctx = make_ctx()
        result = list_drafts(ctx)
        assert "No drafts" in result

    def test_list_drafts_error(self, monkeypatch: pytest.MonkeyPatch):
        from haiku_skills_gmail import list_drafts

        service = self._mock_service()
        service.users().drafts().list.return_value.execute.side_effect = RuntimeError(
            "API error"
        )
        self._patch_service(monkeypatch, service)

        ctx = make_ctx()
        result = list_drafts(ctx)
        assert result.startswith("Error:")
        assert "API error" in result

    def test_list_drafts_individual_fetch_error(self, monkeypatch: pytest.MonkeyPatch):
        from haiku_skills_gmail import list_drafts

        service = self._mock_service()
        service.users().drafts().list.return_value.execute.return_value = {
            "drafts": [{"id": "draft1", "message": {"id": "msg1"}}],
        }
        service.users().drafts().get.return_value.execute.side_effect = RuntimeError(
            "fetch failed"
        )
        self._patch_service(monkeypatch, service)

        ctx = make_ctx()
        result = list_drafts(ctx)
        assert "No drafts" in result

    # -- Labels --

    def test_modify_labels(self, monkeypatch: pytest.MonkeyPatch):
        from haiku_skills_gmail import modify_labels

        service = self._mock_service()
        service.users().messages().modify.return_value.execute.return_value = {
            "id": "msg1",
            "labelIds": ["STARRED"],
        }
        self._patch_service(monkeypatch, service)

        ctx = make_ctx()
        result = modify_labels(
            ctx, "msg1", add_labels="STARRED", remove_labels="UNREAD"
        )

        assert "msg1" in result
        call_kwargs = service.users().messages().modify.call_args.kwargs
        assert call_kwargs["userId"] == "me"
        assert call_kwargs["id"] == "msg1"
        assert call_kwargs["body"] == {
            "addLabelIds": ["STARRED"],
            "removeLabelIds": ["UNREAD"],
        }

    def test_modify_labels_multiple(self, monkeypatch: pytest.MonkeyPatch):
        from haiku_skills_gmail import modify_labels

        service = self._mock_service()
        service.users().messages().modify.return_value.execute.return_value = {
            "id": "msg1",
            "labelIds": ["STARRED", "IMPORTANT"],
        }
        self._patch_service(monkeypatch, service)

        ctx = make_ctx()
        result = modify_labels(ctx, "msg1", add_labels="STARRED, IMPORTANT")
        assert "msg1" in result
        call_kwargs = service.users().messages().modify.call_args.kwargs
        assert call_kwargs["body"]["addLabelIds"] == ["STARRED", "IMPORTANT"]
        assert call_kwargs["body"]["removeLabelIds"] == []

    def test_modify_labels_error(self, monkeypatch: pytest.MonkeyPatch):
        from haiku_skills_gmail import modify_labels

        service = self._mock_service()
        service.users().messages().modify.return_value.execute.side_effect = (
            RuntimeError("modify failed")
        )
        self._patch_service(monkeypatch, service)

        ctx = make_ctx()
        result = modify_labels(ctx, "msg1", add_labels="STARRED")
        assert result.startswith("Error:")
        assert "modify failed" in result

    def test_list_labels(self, monkeypatch: pytest.MonkeyPatch):
        from haiku_skills_gmail import list_labels

        service = self._mock_service()
        service.users().labels().list.return_value.execute.return_value = {
            "labels": [
                {"id": "INBOX", "name": "INBOX", "type": "system"},
                {"id": "Label_1", "name": "Work", "type": "user"},
            ],
        }
        self._patch_service(monkeypatch, service)

        ctx = make_ctx()
        result = list_labels(ctx)
        assert "INBOX" in result
        assert "Work" in result

    def test_list_labels_error(self, monkeypatch: pytest.MonkeyPatch):
        from haiku_skills_gmail import list_labels

        service = self._mock_service()
        service.users().labels().list.return_value.execute.side_effect = RuntimeError(
            "API error"
        )
        self._patch_service(monkeypatch, service)

        ctx = make_ctx()
        result = list_labels(ctx)
        assert result.startswith("Error:")
        assert "API error" in result
