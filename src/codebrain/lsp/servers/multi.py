"""Multi-language reporter that routes to the appropriate language-specific reporter."""

from __future__ import annotations

import logging
from pathlib import Path

from codebrain.core.interfaces import ContextAwareDiagnosticReporter
from codebrain.core.models import Diagnostic, DiagnosticContext
from codebrain.lsp.servers.base import LSPReporter

logger = logging.getLogger(__name__)


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
        for reporter in self._reporters:
            if not reporter.is_running:
                try:
                    await reporter.start()
                except Exception:
                    logger.exception("Failed to start reporter: %s", reporter.name)

    async def stop(self) -> None:
        for reporter in self._reporters:
            if reporter.is_running:
                try:
                    await reporter.stop()
                except Exception:
                    logger.exception("Failed to stop reporter: %s", reporter.name)

    async def get_diagnostics(self, file_path: Path) -> list[Diagnostic]:
        reporter = self.get_reporter_for_file(file_path)
        if reporter is None:
            return []
        if not reporter.is_running:
            logger.warning("Starting reporter on demand: %s", reporter.name)
            await reporter.start()
        try:
            return await reporter.get_diagnostics(file_path)
        except TimeoutError:
            logger.error("Timeout getting diagnostics from %s", reporter.name)
            return []
        except Exception:
            logger.exception("Error getting diagnostics from %s", reporter.name)
            return []

    async def get_all_diagnostics(self) -> dict[Path, list[Diagnostic]]:
        combined: dict[Path, list[Diagnostic]] = {}
        for reporter in self._reporters:
            if not reporter.is_running:
                continue
            try:
                result = await reporter.get_all_diagnostics()
                combined.update(result)
            except Exception:
                logger.exception("Error getting diagnostics from %s", reporter.name)
        return combined

    async def get_context(self, diagnostic: Diagnostic) -> DiagnosticContext:
        file_path = Path(diagnostic.file_path)
        reporter = self.get_reporter_for_file(file_path)
        if reporter is None:
            msg = f"No reporter for {file_path.suffix}"
            raise ValueError(msg)
        if not reporter.is_running:
            await reporter.start()
        try:
            return await reporter.get_context(diagnostic)
        except TimeoutError:
            logger.error("Timeout getting context from %s", reporter.name)
            return DiagnosticContext(diagnostic=diagnostic)
        except Exception:
            logger.exception("Error getting context from %s", reporter.name)
            return DiagnosticContext(diagnostic=diagnostic)

    async def open_file(self, file_path: Path) -> None:
        reporter = self.get_reporter_for_file(file_path)
        if reporter is not None:
            await reporter.open_file(file_path)

    async def update_file(self, file_path: Path, content: str) -> None:
        reporter = self.get_reporter_for_file(file_path)
        if reporter is not None:
            await reporter.update_file(file_path, content)

    async def close_file(self, file_path: Path) -> None:
        reporter = self.get_reporter_for_file(file_path)
        if reporter is not None:
            await reporter.close_file(file_path)
