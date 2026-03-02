import unicodedata
from collections.abc import Callable, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator
from pydantic_ai import Tool
from pydantic_ai.models import Model
from pydantic_ai.toolsets import AbstractToolset


def _validate_skill_name(name: str) -> str:
    name = unicodedata.normalize("NFKC", name)
    if name != name.lower():
        raise ValueError("name must be lowercase")
    if name.startswith("-") or name.endswith("-"):
        raise ValueError("name must not start or end with a hyphen")
    if "--" in name:
        raise ValueError("name must not contain consecutive hyphens")
    if not all(c.isalnum() or c == "-" for c in name):
        raise ValueError(
            "name must contain only lowercase alphanumeric characters and hyphens"
        )
    return name


class SkillMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=64)]
    description: Annotated[str, Field(min_length=1, max_length=1024)]
    license: str | None = None
    compatibility: str | None = Field(None, max_length=500)
    metadata: dict[str, str] = Field(default_factory=dict)
    allowed_tools: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _validate_skill_name(v)

    @field_validator("allowed_tools", mode="before")
    @classmethod
    def validate_allowed_tools(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return v.split() if v.strip() else []
        return v


class SkillSource(StrEnum):
    FILESYSTEM = "filesystem"
    ENTRYPOINT = "entrypoint"
    MCP = "mcp"


class Skill(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    metadata: SkillMetadata
    source: SkillSource
    path: Path | None = None
    instructions: str | None = None
    resources: list[str] = Field(default_factory=list)
    model: str | Model | None = None
    _tools: list[Tool | Callable[..., Any]] = PrivateAttr(default_factory=list)
    _toolsets: list[AbstractToolset[Any]] = PrivateAttr(default_factory=list)
    _state_type: type[BaseModel] | None = PrivateAttr(default=None)
    _state_namespace: str | None = PrivateAttr(default=None)

    def __init__(
        self,
        *,
        tools: Sequence[Tool | Callable[..., Any]] | None = None,
        toolsets: Sequence[AbstractToolset[Any]] | None = None,
        state_type: type[BaseModel] | None = None,
        state_namespace: str | None = None,
        **data: Any,
    ) -> None:
        super().__init__(**data)
        self._tools = list(tools) if tools else []
        self._toolsets = list(toolsets) if toolsets else []
        self._state_type = state_type
        self._state_namespace = state_namespace

    @property
    def tools(self) -> list[Tool | Callable[..., Any]]:
        return self._tools

    @tools.setter
    def tools(self, value: list[Tool | Callable[..., Any]]) -> None:
        self._tools = value

    @property
    def toolsets(self) -> list[AbstractToolset[Any]]:
        return self._toolsets

    @toolsets.setter
    def toolsets(self, value: list[AbstractToolset[Any]]) -> None:
        self._toolsets = value

    @property
    def state_type(self) -> type[BaseModel] | None:
        return self._state_type

    @state_type.setter
    def state_type(self, value: type[BaseModel] | None) -> None:
        self._state_type = value

    @property
    def state_namespace(self) -> str | None:
        return self._state_namespace

    @state_namespace.setter
    def state_namespace(self, value: str | None) -> None:
        self._state_namespace = value
