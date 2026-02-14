# pragma: no cover
from pathlib import Path

from haiku.skills.models import Skill


def run_chat(
    model: str,
    skill_paths: list[Path] | None = None,
    skills: list[Skill] | None = None,
    use_entrypoints: bool = False,
) -> None:
    """Run the chat TUI."""
    try:
        from haiku.skills.chat.app import ChatApp
    except ImportError as e:
        raise ImportError(
            "textual is not installed. Install it with: pip install 'haiku.skills[tui]'"
        ) from e

    from pydantic_ai.models import infer_model

    app = ChatApp(
        model=infer_model(model),
        skill_paths=skill_paths,
        skills=skills,
        use_entrypoints=use_entrypoints,
    )
    app.run()
