# pragma: no cover
import sys


def cli() -> None:
    try:
        import typer  # noqa: F401
        from dotenv import find_dotenv, load_dotenv  # noqa: F401
    except ImportError:
        print(
            "The haiku-skills CLI requires additional dependencies.\n"
            "Install them with: pip install 'haiku.skills[tui]'",
            file=sys.stderr,
        )
        raise SystemExit(1)

    load_dotenv(find_dotenv(usecwd=True))
    app = _build_cli()
    app()


def _build_cli():
    import os
    from pathlib import Path
    from typing import Any

    import typer

    from haiku.skills.registry import SkillRegistry

    app = typer.Typer(help="haiku.skills — Skill-powered AI agents")

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
        errors = registry.discover(paths=paths or None, use_entrypoints=use_entrypoints)
        for error in errors:
            typer.echo(f"Warning: {error.path}: {error}", err=True)
        return registry

    @app.command("validate", help="Validate skill directories against the spec")
    def validate(
        paths: list[Path] = typer.Argument(
            ...,
            help="Path(s) to skill directories containing SKILL.md",
        ),
    ) -> None:
        from skills_ref import validate as skills_ref_validate

        all_valid = True
        for path in paths:
            errors = skills_ref_validate(path)
            if errors:
                all_valid = False
                typer.echo(f"INVALID {path}:", err=True)
                for error in errors:
                    typer.echo(f"  - {error}", err=True)
            else:
                typer.echo(f"VALID   {path}")
        if not all_valid:
            raise typer.Exit(1)

    @app.command("sign", help="Sign a skill directory with sigstore")
    def sign(
        path: Path = typer.Argument(
            ...,
            help="Path to skill directory containing SKILL.md",
        ),
    ) -> None:
        from haiku.skills.signing import sign_skill

        try:
            sign_skill(path)
        except (ImportError, ValueError) as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1)
        typer.echo(f"Signed {path}")

    @app.command("verify", help="Verify a signed skill directory")
    def verify(
        path: Path = typer.Argument(
            ...,
            help="Path to skill directory containing SKILL.md",
        ),
        identity: list[str] = typer.Option(
            [],
            "--identity",
            "-i",
            help="Trusted identity (repeatable)",
        ),
        issuer: list[str] = typer.Option(
            [],
            "--issuer",
            help="OIDC issuer for the corresponding identity (repeatable)",
        ),
        unsafe: bool = typer.Option(
            False,
            "--unsafe",
            help="Verify cryptographic integrity only, without checking signer identity",
        ),
    ) -> None:
        from haiku.skills.signing import (
            TrustedIdentity,
            get_bundle_signer,
            verify_skill,
        )

        if not identity and not unsafe:
            typer.echo(
                "Error: provide --identity/--issuer to verify against a trusted "
                "identity, or --unsafe for integrity-only verification",
                err=True,
            )
            raise typer.Exit(1)

        if identity and len(identity) != len(issuer):
            typer.echo(
                "Error: each --identity must have a corresponding --issuer",
                err=True,
            )
            raise typer.Exit(1)

        identities = (
            [TrustedIdentity(identity=i, issuer=s) for i, s in zip(identity, issuer)]
            if identity
            else None
        )

        try:
            result = verify_skill(path, identities, unsafe=unsafe)
        except ImportError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1)

        if not result:
            typer.echo(f"FAILED   {path}")
            raise typer.Exit(1)

        try:
            signer = get_bundle_signer(path)
        except ImportError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1)

        if signer:
            typer.echo(f"Signed by: {signer.identity} (issuer: {signer.issuer})")

        typer.echo(f"{'INTEGRITY OK' if unsafe else 'VERIFIED'} {path}")

    @app.command("list", help="List discovered skills")
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

    @app.command("chat", help="Launch interactive chat TUI")
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
        skill_model: str | None = typer.Option(
            None,
            "--skill-model",
            help="Model to use for skill sub-agents (e.g. 'ollama:llama3')",
        ),
        no_subagents: bool = typer.Option(
            False,
            "--no-subagents",
            help="Expose skill tools directly instead of delegating to sub-agents",
        ),
        initial_state_path: Path | None = typer.Option(
            None,
            "--initial-state-path",
            help=(
                "Path to YAML file with initial AG-UI state. "
                "Values are deep-merged into each namespace's defaults"
            ),
        ),
    ) -> None:
        model_name = model or os.environ.get("HAIKU_SKILLS_MODEL") or "ollama:gpt-oss"

        import yaml

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

        initial_state: dict[str, Any] | None = None
        if initial_state_path:
            with initial_state_path.open() as state_file:
                initial_state = yaml.safe_load(state_file)

        run_chat(
            model=model_name,
            skills=selected,
            skill_model=skill_model,
            use_subagents=not no_subagents,
            initial_state=initial_state,
        )

    return app
