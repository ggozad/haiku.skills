"""Tests for scripts/bump_version.py."""

import importlib.util
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

# Load bump_version module from scripts/ path
_spec = importlib.util.spec_from_file_location(
    "bump_version", Path(__file__).parent.parent / "scripts" / "bump_version.py"
)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

get_current_version = _mod.get_current_version
update_version_in_file = _mod.update_version_in_file
main = _mod.main


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Create a minimal workspace layout matching haiku.skills."""
    root = tmp_path / "project"
    root.mkdir()

    # Root pyproject.toml
    (root / "pyproject.toml").write_text(
        '[project]\nname = "haiku.skills"\nversion = "0.1.0"\n'
    )

    return root


class TestGetCurrentVersion:
    def test_extracts_version(self, tmp_path: Path):
        f = tmp_path / "pyproject.toml"
        f.write_text('[project]\nname = "test"\nversion = "1.2.3"\n')
        assert get_current_version(f) == "1.2.3"

    def test_raises_on_missing_version(self, tmp_path: Path):
        f = tmp_path / "pyproject.toml"
        f.write_text('[project]\nname = "test"\n')
        with pytest.raises(ValueError, match="Could not find version"):
            get_current_version(f)


class TestUpdateVersionInFile:
    def test_updates_version(self, tmp_path: Path):
        f = tmp_path / "pyproject.toml"
        f.write_text('[project]\nname = "test"\nversion = "0.1.0"\n')
        update_version_in_file(f, "0.2.0")
        assert 'version = "0.2.0"' in f.read_text()

    def test_preserves_other_content(self, tmp_path: Path):
        f = tmp_path / "pyproject.toml"
        content = '[project]\nname = "test"\nversion = "0.1.0"\nfoo = "bar"\n'
        f.write_text(content)
        update_version_in_file(f, "0.2.0")
        result = f.read_text()
        assert 'name = "test"' in result
        assert 'foo = "bar"' in result


class TestMain:
    def test_invalid_version_format(self, workspace: Path):
        with pytest.raises(SystemExit, match="1"):
            with patch("sys.argv", ["bump", "bad"]):
                with patch.object(_mod, "ROOT", workspace):
                    main()

    def test_missing_argument(self, workspace: Path):
        with pytest.raises(SystemExit, match="1"):
            with patch("sys.argv", ["bump"]):
                with patch.object(_mod, "ROOT", workspace):
                    main()

    def test_updates_root_pyproject(self, workspace: Path):
        with (
            patch("sys.argv", ["bump", "0.2.0"]),
            patch.object(_mod, "ROOT", workspace),
            patch("builtins.input", return_value="y"),
            patch("subprocess.run") as mock_run,
        ):
            main()

        # Root version updated
        root_content = (workspace / "pyproject.toml").read_text()
        assert 'version = "0.2.0"' in root_content

        # uv sync was called
        mock_run.assert_called_once_with(["uv", "sync"], check=True, cwd=workspace)

    def test_abort_on_no(self, workspace: Path):
        with (
            patch("sys.argv", ["bump", "0.2.0"]),
            patch.object(_mod, "ROOT", workspace),
            patch("builtins.input", return_value="n"),
        ):
            with pytest.raises(SystemExit, match="0"):
                main()

        # Nothing changed
        root_content = (workspace / "pyproject.toml").read_text()
        assert 'version = "0.1.0"' in root_content

    def test_uv_sync_failure(self, workspace: Path):
        with (
            patch("sys.argv", ["bump", "0.2.0"]),
            patch.object(_mod, "ROOT", workspace),
            patch("builtins.input", return_value="y"),
            patch(
                "subprocess.run",
                side_effect=subprocess.CalledProcessError(1, "uv sync"),
            ),
        ):
            with pytest.raises(SystemExit, match="1"):
                main()

    def test_missing_pyproject(self, tmp_path: Path):
        root = tmp_path / "empty"
        root.mkdir()
        with (
            patch("sys.argv", ["bump", "0.2.0"]),
            patch.object(_mod, "ROOT", root),
        ):
            with pytest.raises(SystemExit, match="1"):
                main()
