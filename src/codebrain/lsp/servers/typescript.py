"""TypeScript language server reporter for TypeScript/JavaScript files."""

from __future__ import annotations

from pathlib import Path

from codebrain.core.models import NodeEnv
from codebrain.lsp.servers.base import LSPReporter

# LSP spec languageId values per extension
_EXT_TO_LANGUAGE_ID: dict[str, str] = {
    ".ts": "typescript",
    ".tsx": "typescriptreact",
    ".js": "javascript",
    ".jsx": "javascriptreact",
}


class TypeScriptReporter(LSPReporter):
    """Diagnostic reporter using typescript-language-server for TS/JS files."""

    _project_markers = ("tsconfig.json", "package.json", "jsconfig.json")

    def __init__(
        self,
        workspace_root: Path,
        server_command: list[str] | None = None,
        node_env: NodeEnv | None = None,
    ) -> None:
        command = server_command or ["typescript-language-server", "--stdio"]
        super().__init__(workspace_root, command, "typescript")
        self._node_env = node_env

    @property
    def name(self) -> str:
        return "typescript-langserver"

    @property
    def supported_extensions(self) -> set[str]:
        return {".ts", ".tsx", ".js", ".jsx"}

    def _language_id_for_file(self, file_path: Path) -> str:
        """Return the correct LSP languageId based on file extension."""
        return _EXT_TO_LANGUAGE_ID.get(file_path.suffix, self._language_id)
