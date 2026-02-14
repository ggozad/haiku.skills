# pragma: no cover
from pathlib import Path

import typer
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))

import os  # noqa: E402

cli = typer.Typer(help="haiku.skills — Skill-powered AI agents")


@cli.command("chat", help="Launch interactive chat TUI")
def chat(
    model: str = typer.Option(
        None,
        "-m",
        "--model",
        help="Model to use (e.g. 'openai:gpt-4o')",
    ),
    skill_path: list[Path] = typer.Option(
        [],
        "-s",
        "--skill-path",
        help="Path to directory containing SKILL.md files (repeatable)",
    ),
    use_entrypoints: bool = typer.Option(
        False,
        "--use-entrypoints",
        help="Discover skills from Python entrypoints",
    ),
) -> None:
    model_name = model or os.environ.get("HAIKU_SKILLS_MODEL") or "ollama:gpt-oss"

    paths = list(skill_path)
    if not paths:
        env_paths = os.environ.get("HAIKU_SKILLS_PATHS", "")
        if env_paths:
            paths = [Path(p) for p in env_paths.split(":") if p]

    if not use_entrypoints:
        use_entrypoints = os.environ.get(
            "HAIKU_SKILLS_USE_ENTRYPOINTS", ""
        ).lower() in ("1", "true", "yes")

    from haiku.skills.chat import run_chat

    run_chat(
        model=model_name,
        skill_paths=paths or None,
        use_entrypoints=use_entrypoints,
    )
