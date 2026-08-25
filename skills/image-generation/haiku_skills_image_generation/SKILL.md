---
name: image-generation
description: Generate images from text prompts using Ollama or Atlas Cloud.
---

# Image Generation

Use the **generate_image** tool to create images from text descriptions.

The tool accepts `width` and `height` parameters (default 1024x1024) and returns the file path of the generated image.

Set `IMAGE_GENERATION_PROVIDER=atlas` and `ATLASCLOUD_API_KEY` to use Atlas Cloud. Ollama remains the default provider. Atlas generation submits once, then polls the prediction endpoint with bounded GET requests.

## Workflow

1. Craft a detailed prompt describing the desired image.
2. Call `generate_image` with the prompt and optional dimensions.
3. The tool returns a file path. Display it to the user as `![description](path)`.

## Guidelines

- Use descriptive, detailed prompts for better results.
- Specify dimensions only when the user requests a non-default size.
