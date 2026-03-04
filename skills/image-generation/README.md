# image-generation

Image generation skill for [haiku.skills](https://github.com/ggozad/haiku.skills) using [Ollama](https://ollama.com/).

## Prerequisites

A running Ollama instance with an image generation model installed.

## Configuration

All configuration is via environment variables:

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_IMAGE_MODEL` | `x/z-image-turbo` | Image generation model |

## Tools

- **generate_image** — Generate an image from a text prompt, returns the file path of the generated image

## Installation

```bash
uv add haiku-skills-image-generation
```
