from pathlib import Path

import pytest
from pydantic_ai.models.openai import OpenAIChatModel

from haiku.skills.agent import resolve_model

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture(scope="module")
def vcr_config():
    return {
        "ignore_localhost": False,
        "filter_headers": ["authorization", "x-api-key", "x-subscription-token"],
        "decode_compressed_response": True,
    }


@pytest.fixture
def ollama_model() -> OpenAIChatModel:
    model = resolve_model("ollama:gpt-oss")
    assert isinstance(model, OpenAIChatModel)
    return model
