---
name: gmail
description: Search, read, send, and manage Gmail emails.
---

# Gmail

Access Gmail to search, read, send, reply to, draft, and organize emails.

## Workflow

1. Use `search_emails` to find relevant emails using Gmail search syntax.
2. Use `read_email` to get the full content of a specific email.
3. Use `send_email` or `reply_to_email` to compose and send messages.
4. Use `create_draft` when the user wants to review before sending.
5. Use `modify_labels` to organize emails (archive, mark read/unread, star, etc.).

## Gmail search syntax

- `from:user@example.com` — emails from a specific sender
- `to:user@example.com` — emails to a specific recipient
- `subject:meeting` — emails with "meeting" in the subject
- `has:attachment` — emails with attachments
- `is:unread` — unread emails
- `is:starred` — starred emails
- `newer_than:7d` — emails from the last 7 days
- `older_than:30d` — emails older than 30 days
- `label:important` — emails with a specific label
- Combine with spaces (AND) or `OR`: `from:alice subject:report`

## Common label operations

- **Archive**: remove label `INBOX`
- **Mark as read**: remove label `UNREAD`
- **Mark as unread**: add label `UNREAD`
- **Star**: add label `STARRED`
- **Unstar**: remove label `STARRED`
- **Move to trash**: add label `TRASH`

## Available Scripts

### `scripts/search_emails.py`

Search Gmail for emails matching a query.

```
--query        (required) Gmail search query.
--max-results  (default: 10) Maximum number of results.
```

### `scripts/read_email.py`

Read the full content of a Gmail email.

```
--message-id   (required) The Gmail message ID.
```

### `scripts/send_email.py`

Send a new Gmail email.

```
--to           (required) Recipient email address.
--subject      (required) Email subject line.
--body         (required) Email body text.
--cc           (default: "") CC recipients (comma-separated).
--bcc          (default: "") BCC recipients (comma-separated).
```

### `scripts/reply_to_email.py`

Reply to a Gmail email.

```
--message-id   (required) The Gmail message ID to reply to.
--body         (required) Reply body text.
--reply-all    (flag) Reply to all recipients.
```

### `scripts/create_draft.py`

Create a Gmail draft email.

```
--to           (required) Recipient email address.
--subject      (required) Email subject line.
--body         (required) Email body text.
--cc           (default: "") CC recipients (comma-separated).
--bcc          (default: "") BCC recipients (comma-separated).
```

### `scripts/list_drafts.py`

List Gmail draft emails.

```
--max-results  (default: 10) Maximum number of drafts.
```

### `scripts/modify_labels.py`

Add or remove labels from a Gmail email.

```
--message-id      (required) The Gmail message ID.
--add-labels      (default: "") Comma-separated label IDs to add.
--remove-labels   (default: "") Comma-separated label IDs to remove.
```

### `scripts/list_labels.py`

List all available Gmail labels. No arguments required.

## Guidelines

- Always confirm with the user before sending emails.
- Prefer creating drafts when unsure about the content.
- When replying, include relevant context from the original email.
- Use `list_labels` to discover available labels before applying them.
