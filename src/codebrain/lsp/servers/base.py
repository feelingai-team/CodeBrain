"""Base LSP reporter with context gathering capabilities."""

from __future__ import annotations

from abc import abstractmethod
from pathlib import Path
from urllib.parse import unquote, urlparse

import lsprotocol.types as lsp

from codebrain.core.interfaces import ContextAwareDiagnosticReporter
from codebrain.core.models import (
    CodeActionSuggestion,
    Diagnostic,
    DiagnosticContext,
    DiagnosticSeverity,
    Range,
    SignatureChangeImpact,
)
from codebrain.lsp.client import LSPClient

# Utility functions


def uri_to_path(uri: str) -> Path:
    parsed = urlparse(uri)
    return Path(unquote(parsed.path))


def lsp_range_to_range(lsp_range: lsp.Range) -> Range:
    raise NotImplementedError


def range_to_lsp_range(range_: Range) -> lsp.Range:
    raise NotImplementedError


def lsp_severity_to_severity(lsp_severity: lsp.DiagnosticSeverity | None) -> DiagnosticSeverity:
    raise NotImplementedError


class LSPReporter(ContextAwareDiagnosticReporter):
    """Base class for all LSP-based diagnostic reporters."""

    def __init__(
        self,
        workspace_root: Path,
        server_command: list[str],
        language_id: str,
        reference_depth: int = 2,
        reference_limit: int = 8,
    ) -> None:
        self._workspace_root = workspace_root
        self._server_command = server_command
        self._language_id = language_id
        self._reference_depth = reference_depth
        self._reference_limit = reference_limit
        self._client: LSPClient | None = None

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def supported_extensions(self) -> set[str]: ...

    @property
    def is_running(self) -> bool:
        return self._client is not None and self._client.is_running

    async def start(self) -> None:
        raise NotImplementedError

    async def stop(self) -> None:
        raise NotImplementedError

    async def open_file(self, file_path: Path) -> None:
        raise NotImplementedError

    async def update_file(self, file_path: Path, content: str) -> None:
        raise NotImplementedError

    async def close_file(self, file_path: Path) -> None:
        raise NotImplementedError

    async def get_diagnostics(self, file_path: Path) -> list[Diagnostic]:
        raise NotImplementedError

    async def get_all_diagnostics(self) -> dict[Path, list[Diagnostic]]:
        raise NotImplementedError

    async def get_code_actions_for_diagnostic(
        self, diagnostic: Diagnostic
    ) -> list[CodeActionSuggestion]:
        raise NotImplementedError

    async def get_context(self, diagnostic: Diagnostic) -> DiagnosticContext:
        raise NotImplementedError

    async def analyze_signature_change_impact(
        self, file_path: Path, line: int, character: int
    ) -> SignatureChangeImpact:
        raise NotImplementedError
