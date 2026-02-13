import logging
from typing import TYPE_CHECKING, Any

import pydantic_ai.models
import pytest

if TYPE_CHECKING:
    from vcr import VCR

setattr(pydantic_ai.models, "ALLOW_MODEL_REQUESTS", False)
logging.getLogger("vcr.cassette").setLevel(logging.WARNING)


@pytest.fixture
def allow_model_requests():
    with pydantic_ai.models.override_allow_model_requests(True):
        yield


def pytest_recording_configure(config: Any, vcr: "VCR"):
    from . import json_body_serializer

    vcr.register_serializer("yaml", json_body_serializer)


@pytest.fixture(scope="module")
def vcr_config():
    return {
        "ignore_localhost": False,
        "filter_headers": ["authorization", "x-api-key"],
        "decode_compressed_response": True,
    }
