"""Pyright language server reporter for Python files."""

from __future__ import annotations

from pathlib import Path

from codebrain.lsp.servers.base import LSPReporter


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
