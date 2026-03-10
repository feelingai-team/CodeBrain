"""Pyright language server reporter for Python files."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from codebrain.lsp.servers.base import LSPReporter

logger = logging.getLogger(__name__)


class PyrightReporter(LSPReporter):
    """Diagnostic reporter using Pyright for Python files."""

    _project_markers = ("pyproject.toml", "setup.py", "setup.cfg", "pyrightconfig.json")

    def __init__(
        self,
        workspace_root: Path,
        server_command: list[str] | None = None,
    ) -> None:
        command = server_command or ["pyright-langserver", "--stdio"]
        super().__init__(workspace_root, command, "python")

    @property
    def name(self) -> str:
        return "pyright"

    @property
    def supported_extensions(self) -> set[str]:
        return {".py", ".pyi"}

    def _build_initialization_options(
        self, effective_root: Path
    ) -> dict[str, Any] | None:
        """Pass venv and extraPaths settings to pyright-langserver."""
        settings: dict[str, Any] = {}

        # Auto-detect venv and configure python path
        venv_dir = effective_root / ".venv"
        if venv_dir.is_dir():
            python_bin = venv_dir / "bin" / "python"
            if python_bin.exists():
                settings["python"] = {"pythonPath": str(python_bin)}
            settings["venvPath"] = str(effective_root)
            settings["venv"] = ".venv"
            logger.info("Pyright: detected venv at %s", venv_dir)

        # Always add the project root as an extra search path so that
        # top-level packages (e.g. `space_llm/`) resolve without needing
        # a pyproject.toml or editable install.
        python_settings: dict[str, Any] = settings.get("python", {})
        python_settings["analysis"] = {
            "extraPaths": [str(effective_root)],
        }
        settings["python"] = python_settings

        return {"settings": settings}
