"""Generate images from text prompts using Ollama or Atlas Cloud."""

import base64
import math
import os
import tempfile
import time
from pathlib import Path
from urllib.parse import quote

import httpx

ATLAS_DEFAULT_BASE_URL = "https://api.atlascloud.ai"
ATLAS_DEFAULT_MODEL = "google/nano-banana-2-lite/text-to-image-developer"
ATLAS_ASPECT_RATIOS = (
    "1:1",
    "3:2",
    "2:3",
    "3:4",
    "4:3",
    "4:5",
    "5:4",
    "9:16",
    "16:9",
    "21:9",
    "4:1",
    "1:4",
    "8:1",
    "1:8",
)


def _atlas_api_root(base_url: str) -> str:
    root = base_url.rstrip("/")
    for suffix in ("/api/v1", "/api", "/v1"):
        if root.lower().endswith(suffix):
            root = root[: -len(suffix)]
            break
    return f"{root}/api/v1"


def _atlas_aspect_ratio(width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive")
    target = width / height
    return min(
        ATLAS_ASPECT_RATIOS,
        key=lambda ratio: abs(
            int(ratio.split(":")[0]) / int(ratio.split(":")[1]) - target
        ),
    )


def _generate_with_ollama(prompt: str, width: int, height: int) -> bytes:
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
    return base64.b64decode(response.json()["image"])


def _generate_with_atlas(prompt: str, width: int, height: int) -> bytes:
    api_key = os.environ.get("ATLASCLOUD_API_KEY")
    if not api_key:
        raise ValueError("ATLASCLOUD_API_KEY is required for the Atlas provider")

    api_root = _atlas_api_root(
        os.environ.get("ATLASCLOUD_BASE_URL", ATLAS_DEFAULT_BASE_URL)
    )
    model = os.environ.get("ATLASCLOUD_IMAGE_MODEL", ATLAS_DEFAULT_MODEL)
    poll_timeout = float(os.environ.get("ATLASCLOUD_POLL_TIMEOUT", "300"))
    poll_interval = float(os.environ.get("ATLASCLOUD_POLL_INTERVAL", "3"))
    if poll_timeout <= 0 or poll_interval <= 0:
        raise ValueError("Atlas poll timeout and interval must be positive")
    headers = {"Authorization": f"Bearer {api_key}"}

    # Generation requests are billable and intentionally submitted exactly once.
    response = httpx.post(
        f"{api_root}/model/generateImage",
        headers=headers,
        json={
            "model": model,
            "prompt": prompt,
            "aspect_ratio": _atlas_aspect_ratio(width, height),
            "resolution": "1k",
        },
        timeout=poll_timeout,
    )
    response.raise_for_status()
    data = response.json().get("data", {})
    prediction_id = data.get("id")
    if not prediction_id:
        raise ValueError("Atlas response did not include a prediction id")

    deadline = time.monotonic() + poll_timeout
    max_polls = min(100, max(1, math.ceil(poll_timeout / max(poll_interval, 0.1))))
    poll_url = f"{api_root}/model/prediction/{quote(str(prediction_id), safe='')}"

    for poll_number in range(max_polls):
        if time.monotonic() >= deadline:
            break
        retry_delay = poll_interval
        try:
            prediction = httpx.get(
                poll_url,
                headers=headers,
                timeout=min(poll_timeout, 30),
            )
            prediction.raise_for_status()
        except (httpx.RequestError, httpx.HTTPStatusError) as exc:
            if isinstance(exc, httpx.HTTPStatusError):
                status_code = exc.response.status_code
                if status_code < 500 and status_code != 429:
                    raise
            retry_delay = min(poll_interval * (2 ** min(poll_number, 4)), 30)
        else:
            result = prediction.json().get("data", {})
            status = str(result.get("status", "")).lower()
            if status in {"completed", "succeeded", "success"}:
                outputs = result.get("outputs") or []
                if not outputs:
                    raise ValueError("Atlas prediction completed without an output URL")
                download = httpx.get(
                    outputs[0],
                    follow_redirects=True,
                    timeout=min(poll_timeout, 60),
                )
                download.raise_for_status()
                return download.content
            if status in {"failed", "canceled", "cancelled"}:
                error = result.get("error") or result.get("message") or status
                raise ValueError(f"Atlas prediction failed: {error}")

        if poll_number + 1 < max_polls:
            time.sleep(retry_delay)

    raise TimeoutError("Atlas prediction polling timed out")


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
    provider = os.environ.get("IMAGE_GENERATION_PROVIDER", "ollama").lower()
    if provider == "ollama":
        image_data = _generate_with_ollama(prompt, width, height)
    elif provider == "atlas":
        image_data = _generate_with_atlas(prompt, width, height)
    else:
        raise ValueError(
            f"Unsupported IMAGE_GENERATION_PROVIDER: {provider}. "
            "Expected 'ollama' or 'atlas'."
        )

    output_dir = Path(tempfile.gettempdir()) / "haiku-skills-images"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"{hash(prompt) & 0xFFFFFFFF:08x}.png"
    output_path.write_bytes(image_data)

    return str(output_path)
