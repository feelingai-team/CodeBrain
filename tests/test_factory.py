"""Tests for factory with SubProject support."""

from __future__ import annotations

from pathlib import Path

from codebrain.core.models import Language, PythonEnv, SubProject, ToolchainConfig
from codebrain.lsp.factory import build_multi_reporter


class TestBuildMultiReporterWithSubProject:
    def test_backward_compatible(self, tmp_path: Path) -> None:
        """Old signature still works."""
        reporter = build_multi_reporter(tmp_path, ["python"])
        assert reporter is not None

    def test_with_sub_project(self, tmp_path: Path) -> None:
        """SubProject passes env to reporters."""
        sp = SubProject(
            root=tmp_path,
            languages=[Language.PYTHON],
            markers={"pyproject.toml": tmp_path / "pyproject.toml"},
            toolchain=ToolchainConfig(
                python_env=PythonEnv(
                    venv_path=tmp_path / ".venv",
                    python_binary=tmp_path / ".venv" / "bin" / "python",
                )
            ),
        )
        reporter = build_multi_reporter(tmp_path, ["python"], sub_project=sp)
        pyright = reporter.get_reporter_for_file(Path("test.py"))
        assert pyright is not None
        assert hasattr(pyright, "_python_env")
        assert pyright._python_env is not None
        assert pyright._python_env.venv_path == tmp_path / ".venv"
