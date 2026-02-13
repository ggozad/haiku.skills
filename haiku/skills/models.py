import re
from enum import StrEnum
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, Field, field_validator

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
    metadata: SkillMetadata
    source: SkillSource
    path: Path | None = None
    instructions: str | None = None


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


class OrchestratorResult(BaseModel):
    answer: str
    tasks: list[Task]
