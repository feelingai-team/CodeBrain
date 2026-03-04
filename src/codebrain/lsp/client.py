"""Generic LSP client communicating over stdio via JSON-RPC 2.0."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import lsprotocol.types as lsp


class LSPClient:
    """Language Server Protocol client over stdio."""

    REQUEST_TIMEOUT: float = 30.0

    def __init__(
        self,
        server_command: list[str],
        workspace_root: Path,
        notification_handlers: (
            dict[str, Callable[[dict[str, Any] | list[Any]], None]] | None
        ) = None,
    ) -> None:
        raise NotImplementedError

    @property
    def is_running(self) -> bool:
        raise NotImplementedError

    @property
    def server_capabilities(self) -> lsp.ServerCapabilities | None:
        raise NotImplementedError

    async def start(self) -> None:
        raise NotImplementedError

    async def stop(self) -> None:
        raise NotImplementedError

    # Text document synchronization

    async def did_open(self, file_path: Path, language_id: str, version: int = 1) -> None:
        raise NotImplementedError

    async def did_change(self, file_path: Path, content: str, version: int) -> None:
        raise NotImplementedError

    async def did_close(self, file_path: Path) -> None:
        raise NotImplementedError

    async def did_save(self, file_path: Path) -> None:
        raise NotImplementedError

    # Language features

    async def get_definition(
        self, file_path: Path, line: int, character: int
    ) -> list[lsp.Location] | list[lsp.LocationLink] | None:
        raise NotImplementedError

    async def get_references(
        self, file_path: Path, line: int, character: int, include_declaration: bool = True
    ) -> list[lsp.Location]:
        raise NotImplementedError

    async def get_hover(
        self, file_path: Path, line: int, character: int
    ) -> lsp.Hover | None:
        raise NotImplementedError

    async def get_code_actions(
        self,
        file_path: Path,
        range_: lsp.Range,
        diagnostics: list[lsp.Diagnostic] | None = None,
        only: list[lsp.CodeActionKind] | None = None,
    ) -> list[lsp.CodeAction | lsp.Command]:
        raise NotImplementedError

    async def resolve_code_action(self, code_action: lsp.CodeAction) -> lsp.CodeAction:
        raise NotImplementedError
