"""Abstract interfaces for diagnostic reporting and context gathering."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Protocol

from codebrain.core.models import Diagnostic, DiagnosticContext, SymbolLocation


class DiagnosticReporter(ABC):
    """Base interface for all diagnostic reporters."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def supported_extensions(self) -> set[str]: ...

    @abstractmethod
    async def get_diagnostics(self, file_path: Path) -> list[Diagnostic]: ...

    @abstractmethod
    async def get_all_diagnostics(self) -> dict[Path, list[Diagnostic]]: ...

    def supports_file(self, file_path: Path) -> bool:
        return file_path.suffix in self.supported_extensions


class ContextProvider(Protocol):
    """Protocol for context gathering (definition, references, hover)."""

    async def get_definition(
        self, file_path: Path, line: int, character: int
    ) -> SymbolLocation | None: ...

    async def get_references(
        self, file_path: Path, line: int, character: int
    ) -> list[SymbolLocation]: ...

    async def get_hover(
        self, file_path: Path, line: int, character: int
    ) -> str | None: ...


class ContextAwareDiagnosticReporter(DiagnosticReporter, ABC):
    """Diagnostic reporter that can also gather rich context for each diagnostic."""

    @abstractmethod
    async def get_context(self, diagnostic: Diagnostic) -> DiagnosticContext: ...
