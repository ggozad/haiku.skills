import re
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator
from pydantic_ai import Tool
from pydantic_ai.toolsets import AbstractToolset

_NAME_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")


def _validate_skill_name(name: str) -> str:
    if "--" in name:
        raise ValueError("name must not contain consecutive hyphens")
    if not _NAME_PATTERN.match(name):
        raise ValueError(
            "name must be lowercase alphanumeric with hyphens, "
            "not starting or ending with a hyphen"
        )
    return name


class SkillMetadata(BaseModel):
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
    _tools: list = PrivateAttr(default_factory=list)
    _toolsets: list = PrivateAttr(default_factory=list)

    def __init__(
        self,
        *,
        tools: list[Tool | Callable[..., Any]] | None = None,
        toolsets: list[AbstractToolset[Any]] | None = None,
        **data: Any,
    ) -> None:
        super().__init__(**data)
        self._tools = tools or []
        self._toolsets = toolsets or []

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


class TaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class Task(BaseModel):
    id: str
    description: str
    skills: list[str]
    status: TaskStatus = TaskStatus.PENDING
    result: str | None = None
    error: str | None = None


class DecompositionPlan(BaseModel):
    tasks: list[Task]
    reasoning: str


class OrchestratorPhase(StrEnum):
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    SYNTHESIZING = "synthesizing"


class OrchestratorState(BaseModel):
    phase: OrchestratorPhase = OrchestratorPhase.IDLE
    plan: DecompositionPlan | None = None
    tasks: list[Task] = Field(default_factory=list)
    result: "OrchestratorResult | None" = None


class OrchestratorResult(BaseModel):
    answer: str
    tasks: list[Task]
