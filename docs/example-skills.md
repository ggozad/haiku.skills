# Example skills

haiku.skills ships with several skill packages under `skills/`. They serve as both ready-to-use tools and reference implementations — each one demonstrates a different pattern (script tools, in-process tools with state, OAuth flows, external APIs).

## Using example skills

The recommended way is to install them as entrypoint packages:

```bash
uv add haiku-skills-web
```

```python
from haiku.skills import SkillToolset

toolset = SkillToolset(use_entrypoints=True)
```

This gives you in-process tools with full state access, versioned dependencies, and zero-config discovery.

### Using as filesystem skills

You can also point `skill_paths` at the skill directories directly — useful for modifying the SKILL.md instructions or scripts without forking the package:

```python
from pathlib import Path
from haiku.skills import SkillToolset

toolset = SkillToolset(skill_paths=[Path("./skills/web/haiku_skills_web/web")])
```

Note that filesystem loading only picks up script tools (run as subprocesses). In-process tools, per-skill state, and any Python dependencies declared in the package are not available — those require entrypoint installation.

## web

Web search via [Brave Search API](https://brave.com/search/api/) and page content extraction via [trafilatura](https://trafilatura.readthedocs.io/).

```bash
uv add haiku-skills-web
```

Requires `BRAVE_API_KEY` environment variable for search functionality.

## image-generation

Image generation via [Ollama](https://ollama.com/).

```bash
uv add haiku-skills-image-generation
```

## code-execution

Sandboxed Python execution via [pydantic-monty](https://github.com/pydantic/pydantic-monty) with a built-in `await llm(prompt)` function for LLM reasoning (classify, summarize, extract).

```bash
uv add haiku-skills-code-execution
```

## gmail

Gmail access via the [Google Gmail API](https://developers.google.com/gmail/api) with OAuth2 authentication. Search, read, send, reply, draft, and label emails.

```bash
uv add haiku-skills-gmail
```

Requires Google Cloud OAuth2 credentials. Configure via environment variables:

- `EMAIL_CREDENTIALS_PATH` — Path to OAuth2 credentials file (default: `~/.config/haiku-skills-gmail/credentials.json`)
- `EMAIL_TOKEN_PATH` — Path to cached OAuth2 token (default: `~/.config/haiku-skills-gmail/token.json`)

On first run, a browser window opens for OAuth2 authorization. The token is cached for subsequent runs. See the [skill README](https://github.com/ggozad/haiku.skills/tree/main/skills/gmail) for Google Cloud setup instructions.

## notifications

Push notifications via [ntfy.sh](https://ntfy.sh/). Send and receive messages on topic-based channels — no signup required.

```bash
uv add haiku-skills-notifications
```

Requires an ntfy.sh server. The public instance at `https://ntfy.sh` works out of the box. Configure via environment variables:

- `NTFY_SERVER` — ntfy server base URL (default: `https://ntfy.sh`)
- `NTFY_TOKEN` — Bearer token for authenticated topics (optional)

Tools: `send_notification`, `read_notifications`. See the [skill README](https://github.com/ggozad/haiku.skills/tree/main/skills/notifications) for self-hosted setup instructions.

## External: RAG

For retrieval-augmented generation, the separate [haiku.rag](https://github.com/ggozad/haiku.rag) project provides a full RAG skill for haiku.skills. It is not part of this repository — install it independently:

```bash
uv add haiku.rag
```
