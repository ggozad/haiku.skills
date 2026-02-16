# pragma: no cover
from pathlib import Path

import typer
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))

import os  # noqa: E402

from haiku.skills.registry import SkillRegistry  # noqa: E402

cli = typer.Typer(help="haiku.skills — Skill-powered AI agents")


def _resolve_discovery(
    skill_path: list[Path],
    use_entrypoints: bool,
) -> SkillRegistry:
    """Discover skills from CLI options and environment variables."""
    paths = list(skill_path)
    if not paths:
        env_paths = os.environ.get("HAIKU_SKILLS_PATHS", "")
        if env_paths:
            paths = [Path(p) for p in env_paths.split(":") if p]

    if not use_entrypoints:
        use_entrypoints = os.environ.get(
            "HAIKU_SKILLS_USE_ENTRYPOINTS", ""
        ).lower() in ("1", "true", "yes")

    registry = SkillRegistry()
    registry.discover(paths=paths or None, use_entrypoints=use_entrypoints)
    return registry


@cli.command("list", help="List discovered skills")
def list_skills(
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
    registry = _resolve_discovery(skill_path, use_entrypoints)
    for meta in registry.list_metadata():
        typer.echo(f"{meta.name} — {meta.description}")


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
    skill: list[str] = typer.Option(
        [],
        "-k",
        "--skill",
        help="Skill name to activate (repeatable, filters discovered skills)",
    ),
) -> None:
    model_name = model or os.environ.get("HAIKU_SKILLS_MODEL") or "ollama:gpt-oss"

    from haiku.skills.chat import run_chat

    registry = _resolve_discovery(skill_path, use_entrypoints)

    if skill:
        selected = []
        for name in skill:
            s = registry.get(name)
            if s is None:
                typer.echo(f"Unknown skill: {name}", err=True)
                raise typer.Exit(1)
            selected.append(s)
    else:
        selected = [s for n in registry.names if (s := registry.get(n)) is not None]

    run_chat(model=model_name, skills=selected)
