import logging
import re
from typing import TYPE_CHECKING, Any

import pydantic_ai.models
import pytest

if TYPE_CHECKING:
    from vcr import VCR
    from vcr import request as vcr_request

setattr(pydantic_ai.models, "ALLOW_MODEL_REQUESTS", False)
logging.getLogger("vcr.cassette").setLevel(logging.WARNING)


@pytest.fixture
def allow_model_requests():
    with pydantic_ai.models.override_allow_model_requests(True):
        yield


_OLLAMA_HOST_RE = re.compile(r"(https?://)([^/]+)(:\d+)")
_DEFAULT_OLLAMA = "127.0.0.1:11434"


def pytest_recording_configure(config: Any, vcr: "VCR"):
    from tests import json_body_serializer

    vcr.register_serializer("yaml", json_body_serializer)

    def normalize_ollama_host(request: "vcr_request.Request") -> "vcr_request.Request":
        """Rewrite non-default Ollama hosts to localhost so cassettes are portable."""
        if "/v1/chat/completions" in request.uri:
            request.uri = _OLLAMA_HOST_RE.sub(rf"\g<1>{_DEFAULT_OLLAMA}", request.uri)
            if "host" in request.headers:
                request.headers["host"] = _DEFAULT_OLLAMA
        return request

    vcr.before_record_request = normalize_ollama_host


@pytest.fixture(scope="module")
def vcr_config():
    return {
        "ignore_localhost": False,
        "filter_headers": ["authorization", "x-api-key", "x-subscription-token"],
        "decode_compressed_response": True,
    }
