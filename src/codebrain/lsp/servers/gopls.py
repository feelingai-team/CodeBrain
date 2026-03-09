"""Go language server reporter for Go files."""

from __future__ import annotations

from pathlib import Path

from codebrain.lsp.servers.base import LSPReporter


class GoplsReporter(LSPReporter):
    """Diagnostic reporter using gopls for Go files."""

    def __init__(
        self,
        workspace_root: Path,
        server_command: list[str] | None = None,
    ) -> None:
        command = server_command or ["gopls", "serve"]
        super().__init__(workspace_root, command, "go")

    @property
    def name(self) -> str:
        return "gopls"

    @property
    def supported_extensions(self) -> set[str]:
        return {".go"}
