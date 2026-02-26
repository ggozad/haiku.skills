from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import RunContext
from pydantic_ai.toolsets import FunctionToolset, ToolsetTool


class TaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class Task(BaseModel):
    id: str
    subject: str
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    depends_on: list[str] = Field(default_factory=list)


class TaskToolset(FunctionToolset[Any]):
    """Toolset for orchestrating multi-step workflows via task management."""

    def __init__(self) -> None:
        super().__init__()
        self._tasks: dict[str, Task] = {}
        self._counter: int = 0
        self._register_tools()

    def reset(self) -> None:
        """Clear all tasks. Counter keeps incrementing to avoid ID collisions."""
        self._tasks.clear()

    async def get_tools(self, ctx: RunContext[Any]) -> dict[str, ToolsetTool[Any]]:
        if ctx.run_step == 0:
            self.reset()
        return await super().get_tools(ctx)

    async def create_task(
        self,
        ctx: RunContext[Any],
        subject: str,
        description: str = "",
        depends_on: list[str] | None = None,
    ) -> str:
        """Create a task to track a step in a multi-skill workflow.

        Args:
            subject: Brief description of the task.
            description: Detailed description of what needs to be done.
            depends_on: List of task IDs that must complete before this one.
        """
        deps = depends_on or []
        for dep_id in deps:
            if dep_id not in self._tasks:
                return f"Error: dependency '{dep_id}' does not exist"
        self._counter += 1
        task_id = str(self._counter)
        self._tasks[task_id] = Task(
            id=task_id,
            subject=subject,
            description=description,
            depends_on=deps,
        )
        return f"Task {task_id} created: {subject}"

    async def update_task(
        self,
        ctx: RunContext[Any],
        task_id: str,
        status: str | None = None,
    ) -> str:
        """Update the status of a task.

        Args:
            task_id: The ID of the task to update.
            status: New status (pending, in_progress, completed, failed).
        """
        task = self._tasks.get(task_id)
        if task is None:
            return f"Error: task '{task_id}' not found"
        if status is not None:
            try:
                task.status = TaskStatus(status)
            except ValueError:
                valid = ", ".join(s.value for s in TaskStatus)
                return f"Error: invalid status '{status}'. Valid: {valid}"
        return f"Task {task_id} updated"

    async def list_tasks(self, ctx: RunContext[Any]) -> str:
        """List all tasks with their status, dependencies, and results."""
        if not self._tasks:
            return "No tasks."
        lines: list[str] = []
        for task in self._tasks.values():
            parts = [f"[{task.id}] {task.subject} ({task.status})"]
            if task.depends_on:
                parts.append(f"  depends on: {', '.join(task.depends_on)}")
            lines.append("\n".join(parts))
        return "\n".join(lines)

    def _register_tools(self) -> None:
        self.tool(self.create_task)
        self.tool(self.update_task)
        self.tool(self.list_tasks)
