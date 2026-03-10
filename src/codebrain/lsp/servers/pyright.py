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
        """Build pyright-langserver settings.

        Settings are sent both as initializationOptions and via
        workspace/didChangeConfiguration (pyright reads the latter).

        NOTE: python.analysis.extraPaths via LSP is ignored when a
        pyrightconfig.json exists — in that case pyright reads extraPaths
        from the config file instead.
        """
        python_settings: dict[str, Any] = {
            "analysis": {
                # Add project root as import search path so top-level
                # packages resolve without pyproject.toml/editable install
                "extraPaths": [str(effective_root)],
                "autoSearchPaths": True,
            },
        }

        # Auto-detect venv and configure python path
        venv_dir = effective_root / ".venv"
        if venv_dir.is_dir():
            python_bin = venv_dir / "bin" / "python"
            if python_bin.exists():
                python_settings["pythonPath"] = str(python_bin)
            python_settings["venvPath"] = str(effective_root)
            logger.info("Pyright: detected venv at %s", venv_dir)

        return {"settings": {"python": python_settings}}
