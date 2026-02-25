# /// script
# requires-python = ">=3.13"
# dependencies = ["httpx"]
# ///
"""Generate images from text prompts using Ollama."""

import base64
import os
import sys
import tempfile
from pathlib import Path

import httpx


def main(
    prompt: str,
    width: int = 1024,
    height: int = 1024,
) -> str:
    """Generate an image from a text prompt.

    Args:
        prompt: The text description of the image to generate.
        width: Image width in pixels.
        height: Image height in pixels.
    """
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    model = os.environ.get("OLLAMA_IMAGE_MODEL", "x/z-image-turbo")

    response = httpx.post(
        f"{host}/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "width": width,
            "height": height,
            "stream": False,
        },
        timeout=300,
    )
    response.raise_for_status()
    data = response.json()

    image_data = base64.b64decode(data["image"])

    output_dir = Path(tempfile.gettempdir()) / "haiku-skills-images"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"{hash(prompt) & 0xFFFFFFFF:08x}.png"
    output_path.write_bytes(image_data)

    return f"![{prompt}]({output_path})"


if __name__ == "__main__":
    prompt = sys.argv[1]
    width = int(sys.argv[2]) if len(sys.argv) > 2 else 1024
    height = int(sys.argv[3]) if len(sys.argv) > 3 else 1024
    print(main(prompt, width, height))
