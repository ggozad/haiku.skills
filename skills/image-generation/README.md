# image-generation

Image generation skill for [haiku.skills](https://github.com/ggozad/haiku.skills) using [Ollama](https://ollama.com/) or Atlas Cloud.

## Prerequisites

Use either a running Ollama instance with an image generation model installed, or an Atlas Cloud API key.

## Configuration

All configuration is via environment variables:

| Variable | Default | Description |
|---|---|---|
| `IMAGE_GENERATION_PROVIDER` | `ollama` | Image provider: `ollama` or `atlas` |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_IMAGE_MODEL` | `x/z-image-turbo` | Image generation model |
| `ATLASCLOUD_API_KEY` | — | Atlas Cloud API key (required for `atlas`) |
| `ATLASCLOUD_BASE_URL` | `https://api.atlascloud.ai` | Atlas Cloud API base URL |
| `ATLASCLOUD_IMAGE_MODEL` | `google/nano-banana-2-lite/text-to-image-developer` | Atlas Cloud text-to-image model |
| `ATLASCLOUD_POLL_TIMEOUT` | `300` | Maximum prediction polling time in seconds |
| `ATLASCLOUD_POLL_INTERVAL` | `3` | Delay between prediction GET requests |

Atlas Cloud uses asynchronous generation. The skill submits the billable generation POST exactly once and only retries bounded prediction GET requests. Requested width and height are mapped to the nearest supported aspect ratio.

## Tools

- **generate_image** — Generate an image from a text prompt, returns the file path of the generated image

## Installation

```bash
uv add haiku-skills-image-generation
```
