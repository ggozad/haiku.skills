#!/usr/bin/env python3
"""Version bumping script for haiku.skills."""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def get_current_version(file_path: Path) -> str:
    """Extract current version from pyproject.toml."""
    content = file_path.read_text()
    match = re.search(r'^version = "([^"]+)"', content, re.MULTILINE)
    if not match:
        raise ValueError(f"Could not find version in {file_path}")
    return match.group(1)


def update_version_in_file(file_path: Path, new_version: str) -> None:
    """Update version in a pyproject.toml file."""
    content = file_path.read_text()
    updated = re.sub(
        r'^version = "[^"]+"',
        f'version = "{new_version}"',
        content,
        flags=re.MULTILINE,
    )
    file_path.write_text(updated)
    print(f"  Updated {file_path}")


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/bump_version.py <new_version>")
        print("Example: python scripts/bump_version.py 0.2.0")
        sys.exit(1)

    new_version = sys.argv[1]

    if not re.match(r"^\d+\.\d+\.\d+$", new_version):
        print(f"Error: Invalid version format '{new_version}'")
        print("Version must be in format: X.Y.Z (e.g., 0.2.0)")
        sys.exit(1)

    root_pyproject = ROOT / "pyproject.toml"
    if not root_pyproject.exists():
        print(f"Error: {root_pyproject} not found")
        sys.exit(1)

    current_version = get_current_version(root_pyproject)
    print(f"Current version: {current_version}")
    print(f"New version: {new_version}")
    print()

    response = input("Proceed with version bump? [y/N] ")
    if response.lower() != "y":
        print("Aborted.")
        sys.exit(0)

    print()
    update_version_in_file(root_pyproject, new_version)

    print()
    print("Running uv sync...")
    try:
        subprocess.run(["uv", "sync"], check=True, cwd=ROOT)
        print("Lock file updated")
    except subprocess.CalledProcessError as e:
        print(f"Error: uv sync failed with exit code {e.returncode}")
        sys.exit(1)

    print()
    print(f"Version bumped from {current_version} to {new_version}")


if __name__ == "__main__":
    main()
