---
name: notifications
description: Send and receive push notifications via ntfy.sh.
---

# Notifications

Use the **send_notification** tool to publish push notifications to an ntfy.sh topic.
Use the **read_notifications** tool to poll and read cached messages from a topic.

## Workflow

1. Use `send_notification` to send a message to a topic.
2. Use `read_notifications` to check for incoming messages on a topic.
3. Topics are shared — anyone subscribed to the same topic receives the messages.

## Available Scripts

### `scripts/send_notification.py`

Send a push notification via ntfy.sh.

```
--topic     (required) The ntfy topic to publish to.
--message   (required) The notification message body.
--title     (default: "") Optional notification title.
--priority  (default: "default") Priority (1-5 or min/low/default/high/max).
--server    (default: "") ntfy server URL (defaults to https://ntfy.sh).
```

### `scripts/read_notifications.py`

Read cached messages from an ntfy.sh topic.

```
--topic     (required) The ntfy topic to read from.
--since     (default: "10m") How far back to look (e.g. "10m", "1h", "all").
--server    (default: "") ntfy server URL (defaults to https://ntfy.sh).
```

## Guidelines

- Choose descriptive, hard-to-guess topic names to avoid collisions.
- Use the `title` parameter for structured notifications.
- Use `priority` to signal urgency (1=min, 3=default, 5=max).
- The `since` parameter on `read_notifications` controls how far back to look (e.g. "10m", "1h", "all").
