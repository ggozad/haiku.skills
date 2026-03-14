# email

Gmail email skill for [haiku.skills](https://github.com/ggozad/haiku.skills) using the Google Gmail API.

Enables agents to search, read, send, reply to, draft, and organize Gmail emails with OAuth2 authentication.

## Prerequisites

### Google Cloud credentials

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project (or select an existing one)
3. Enable the **Gmail API**
4. Create OAuth 2.0 credentials (Desktop application)
5. Download the credentials JSON file

### Configuration

Place your credentials file and configure via environment variables:

| Variable | Default | Description |
|---|---|---|
| `EMAIL_CREDENTIALS_PATH` | `~/.config/haiku-skills-email/credentials.json` | Path to OAuth2 credentials file |
| `EMAIL_TOKEN_PATH` | `~/.config/haiku-skills-email/token.json` | Path to cached OAuth2 token |

On first run, a browser window will open for OAuth2 authorization. The token is cached for subsequent runs.

## Tools

- **search_emails** — Search emails using Gmail search syntax
- **read_email** — Read the full content of an email
- **send_email** — Send a new email
- **reply_to_email** — Reply to an email thread
- **create_draft** — Create a draft email
- **list_drafts** — List existing drafts
- **modify_labels** — Add or remove labels from an email
- **list_labels** — List all available labels

## Installation

```bash
uv add haiku-skills-email
```
