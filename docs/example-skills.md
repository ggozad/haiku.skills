# Example skills

haiku.skills ships with several entrypoint skill packages under `skills/`. Each one demonstrates a different pattern and can be used as a reference implementation.

## Using example skills

Install them as Python packages and enable entrypoint discovery:

```bash
uv add haiku-skills-web
```

```python
from haiku.skills import SkillToolset

toolset = SkillToolset(use_entrypoints=True)
```

## web

Web search via [Brave Search API](https://brave.com/search/api/) and page content extraction via [trafilatura](https://trafilatura.readthedocs.io/).

```bash
uv add haiku-skills-web
```

Tools: `search`, `fetch_page`. Requires `BRAVE_API_KEY` environment variable.

## image-generation

Image generation via [Ollama](https://ollama.com/).

```bash
uv add haiku-skills-image-generation
```

Tools: `generate_image`. Returns the file path of the generated image.

## code-execution

Sandboxed Python execution via [pydantic-monty](https://github.com/pydantic/pydantic-monty) with a built-in `await llm(prompt)` function for LLM reasoning.

```bash
uv add haiku-skills-code-execution
```

Tools: `run_code`.

## gmail

Gmail access via the [Google Gmail API](https://developers.google.com/gmail/api) with OAuth2 authentication.

```bash
uv add haiku-skills-gmail
```

Requires Google Cloud OAuth2 credentials. Configure via environment variables:

- `EMAIL_CREDENTIALS_PATH` — Path to OAuth2 credentials file (default: `~/.config/haiku-skills-gmail/credentials.json`)
- `EMAIL_TOKEN_PATH` — Path to cached OAuth2 token (default: `~/.config/haiku-skills-gmail/token.json`)

Tools: `search_emails`, `read_email`, `send_email`, `reply_to_email`, `create_draft`, `list_drafts`, `modify_labels`, `list_labels`.

## notifications

Push notifications via [ntfy.sh](https://ntfy.sh/).

```bash
uv add haiku-skills-notifications
```

Configure via environment variables:

- `NTFY_SERVER` — ntfy server base URL (default: `https://ntfy.sh`)
- `NTFY_TOKEN` — Bearer token for authenticated topics (optional)

Tools: `send_notification`, `read_notifications`.

## External: RAG

For retrieval-augmented generation, the separate [haiku.rag](https://github.com/ggozad/haiku.rag) project provides a RAG skill. Install independently:

```bash
uv add haiku.rag
```
