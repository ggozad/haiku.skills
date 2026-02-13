import pydantic_ai.models
import pytest

setattr(pydantic_ai.models, "ALLOW_MODEL_REQUESTS", False)


@pytest.fixture
def allow_model_requests():
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pydantic_ai.models, "ALLOW_MODEL_REQUESTS", True)
        yield
