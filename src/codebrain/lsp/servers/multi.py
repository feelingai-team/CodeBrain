"""Multi-language reporter that routes to the appropriate language-specific reporter."""

from __future__ import annotations

from pathlib import Path

from codebrain.core.interfaces import ContextAwareDiagnosticReporter
from codebrain.core.models import Diagnostic, DiagnosticContext
from codebrain.lsp.servers.base import LSPReporter


class MultiLanguageReporter(ContextAwareDiagnosticReporter):
    """Routes diagnostic requests to the correct language-specific LSP reporter."""

    def __init__(
        self,
        workspace_root: Path,
        reporters: list[LSPReporter] | None = None,
    ) -> None:
        self._workspace_root = workspace_root
        self._reporters: list[LSPReporter] = []
        self._extension_map: dict[str, LSPReporter] = {}
        for reporter in reporters or []:
            self.add_reporter(reporter)

    def add_reporter(self, reporter: LSPReporter) -> None:
        for ext in reporter.supported_extensions:
            if ext in self._extension_map:
                raise ValueError(
                    f"Extension {ext} already handled by {self._extension_map[ext].name}"
                )
            self._extension_map[ext] = reporter
        self._reporters.append(reporter)

    def get_reporter_for_file(self, file_path: Path) -> LSPReporter | None:
        return self._extension_map.get(file_path.suffix)

    @property
    def name(self) -> str:
        return "multi-language"

    @property
    def supported_extensions(self) -> set[str]:
        return set(self._extension_map.keys())

    @property
    def is_running(self) -> bool:
        return any(r.is_running for r in self._reporters)

    async def start(self) -> None:
        raise NotImplementedError

    async def stop(self) -> None:
        raise NotImplementedError

    async def get_diagnostics(self, file_path: Path) -> list[Diagnostic]:
        raise NotImplementedError

    async def get_all_diagnostics(self) -> dict[Path, list[Diagnostic]]:
        raise NotImplementedError

    async def get_context(self, diagnostic: Diagnostic) -> DiagnosticContext:
        raise NotImplementedError

    async def open_file(self, file_path: Path) -> None:
        raise NotImplementedError

    async def update_file(self, file_path: Path, content: str) -> None:
        raise NotImplementedError

    async def close_file(self, file_path: Path) -> None:
        raise NotImplementedError
