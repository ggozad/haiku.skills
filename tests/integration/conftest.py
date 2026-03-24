import pytest
from pydantic_ai.models.openai import OpenAIChatModel

from haiku.skills.agent import resolve_model


@pytest.fixture
def ollama_model() -> OpenAIChatModel:
    model = resolve_model("ollama:gpt-oss")
    assert isinstance(model, OpenAIChatModel)
    return model
