# notifications

Push notifications skill for [haiku.skills](https://github.com/ggozad/haiku.skills) using [ntfy.sh](https://ntfy.sh/).

## Prerequisites

An [ntfy.sh](https://ntfy.sh/) server. The public instance at `https://ntfy.sh` works with no signup. For local development, run ntfy in Docker:

```bash
# Minimal — runs on port 2586, no auth, ephemeral cache
docker run -p 2586:80 -it binwiederhier/ntfy serve

# With persistent cache
docker run \
  -v ntfy-cache:/var/cache/ntfy \
  -p 2586:80 \
  binwiederhier/ntfy serve \
  --cache-file /var/cache/ntfy/cache.db

# Test: send a message
curl -d "Hello from ntfy!" localhost:2586/test-topic

# Test: read messages
curl "localhost:2586/test-topic/json?poll=1&since=all"
```

## Configuration

All configuration is via environment variables:

| Variable | Default | Description |
|---|---|---|
| `NTFY_SERVER` | `https://ntfy.sh` | ntfy server base URL |
| `NTFY_TOKEN` | — | Bearer token for authenticated topics (optional) |

## Tools

- **send_notification** — Publish a push notification to an ntfy.sh topic
- **read_notifications** — Poll and read cached messages from an ntfy.sh topic

## Installation

```bash
uv add haiku-skills-notifications
```
