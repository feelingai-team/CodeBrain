"""Clangd language server reporter for C/C++ files."""

from __future__ import annotations

from pathlib import Path

from codebrain.core.models import CppEnv
from codebrain.lsp.servers.base import LSPReporter


class ClangdReporter(LSPReporter):
    """Diagnostic reporter using Clangd for C/C++ files."""

    _project_markers = ("compile_commands.json", "CMakeLists.txt", ".clangd")

    def __init__(
        self,
        workspace_root: Path,
        server_command: list[str] | None = None,
        cpp_env: CppEnv | None = None,
    ) -> None:
        command = server_command or ["clangd", "--background-index"]
        super().__init__(workspace_root, command, "cpp")
        self._cpp_env = cpp_env

    @property
    def name(self) -> str:
        return "clangd"

    @property
    def supported_extensions(self) -> set[str]:
        return {".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".hxx"}
