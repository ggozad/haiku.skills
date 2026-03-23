"""Shared Gmail message parsing and formatting utilities."""

import base64
from email.mime.text import MIMEText
from typing import Any


def _get_header(headers: list[dict[str, str]], name: str) -> str:
    for header in headers:
        if header["name"] == name:
            return header["value"]
    return ""


def _parse_email_body(payload: dict[str, Any]) -> str:
    mime_type = payload.get("mimeType", "")

    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode()
        return ""

    if mime_type.startswith("multipart/"):
        for part in payload.get("parts", []):
            result = _parse_email_body(part)
            if result:
                return result

    return ""


def _build_message(
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
    in_reply_to: str = "",
    references: str = "",
) -> dict[str, str]:
    message = MIMEText(body)
    message["To"] = to
    message["Subject"] = subject
    if cc:
        message["Cc"] = cc
    if bcc:
        message["Bcc"] = bcc
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
    if references:
        message["References"] = references

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return {"raw": raw}


def _format_email_summary(msg: dict[str, Any]) -> str:
    headers = msg.get("payload", {}).get("headers", [])
    subject = _get_header(headers, "Subject")
    sender = _get_header(headers, "From")
    date = _get_header(headers, "Date")
    snippet = msg.get("snippet", "")
    msg_id = msg.get("id", "")

    return (
        f"ID: {msg_id}\n"
        f"From: {sender}\n"
        f"Subject: {subject}\n"
        f"Date: {date}\n"
        f"Snippet: {snippet}"
    )
