# haiku-skills-sandbox

Docker sandbox skill for [haiku.skills](https://github.com/ggozad/haiku.skills). Executes Python code in an isolated Docker container with pre-installed data science packages and filesystem access.

## Prerequisites

Build the Docker image (once):

```bash
docker build -t haiku-skills-sandbox:latest skills/sandbox/haiku_skills_sandbox/
```

## Usage

### Via entry point discovery

```bash
HAIKU_SKILLS_SANDBOX_WORKSPACE=/path/to/data haiku-skills chat
```

### Programmatic

```python
from pathlib import Path
from haiku_skills_sandbox import create_skill

skill = create_skill(
    workspace=Path("/path/to/data"),  # mounted at /workspace in the container
    idle_timeout=1800,                # stop container after 30min idle (default: 1h)
    image="my-custom-image:latest",   # custom Docker image (default: haiku-skills-sandbox:latest)
)
```

## Configuration

| Parameter | Env var | Default | Description |
|-----------|---------|---------|-------------|
| `workspace` | `HAIKU_SKILLS_SANDBOX_WORKSPACE` | None | Host directory mounted at `/workspace` in the container |
| `idle_timeout` | `HAIKU_SKILLS_SANDBOX_IDLE_TIMEOUT` | 3600 | Seconds of inactivity before the container is stopped |
| `image` | `HAIKU_SKILLS_SANDBOX_IMAGE` | `haiku-skills-sandbox:latest` | Docker image to use for the container |

Priority: `create_skill()` argument > environment variable > default.

## Container lifecycle

- Containers start lazily on the first tool call
- Session binding via `SandboxState.session_id` — the same AG-UI thread reuses the same container
- Idle containers are stopped automatically (checked on each tool call)
- All containers are stopped on process exit via `atexit`
- When workspace is mounted, files persist on the host — restarting a container loses nothing

## Pre-installed packages

The `haiku-skills-sandbox:latest` image includes: pandas, numpy, scipy, matplotlib.

## Security considerations

- **Network access:** Containers have full network access (Docker bridge networking) by default.
- **Command execution:** `ConsoleToolset` is configured with `require_execute_approval=False` — the LLM can run arbitrary commands inside the container without user confirmation. Docker provides the isolation boundary.
- **Workspace access:** When a workspace is mounted, the container has full read/write access to that host directory. The LLM can read, modify, or delete any file in the mounted workspace.
- **Container user:** The container runs as root. Docker container isolation is the security boundary, not OS-level user separation.
