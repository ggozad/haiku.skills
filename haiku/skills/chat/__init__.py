# pragma: no cover
from pathlib import Path

from haiku.skills.models import Skill


def run_chat(
    model: str,
    skill_paths: list[Path] | None = None,
    skills: list[Skill] | None = None,
    use_entrypoints: bool = False,
    skill_model: str | None = None,
) -> None:
    """Run the chat TUI."""
    try:
        from haiku.skills.chat.app import ChatApp
    except ImportError as e:
        raise ImportError(
            "textual is not installed. Install it with: pip install 'haiku.skills[tui]'"
        ) from e

    from haiku.skills.agent import resolve_model

    app = ChatApp(
        model=resolve_model(model),
        skill_paths=skill_paths,
        skills=skills,
        use_entrypoints=use_entrypoints,
        skill_model=skill_model,
    )
    app.run()
