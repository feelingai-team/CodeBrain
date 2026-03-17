"""FallbackChain — wraps a primary LSP reporter with a CLI fallback."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from codebrain.core.interfaces import ContextAwareDiagnosticReporter, DiagnosticReporter
from codebrain.core.models import Diagnostic, DiagnosticContext

logger = logging.getLogger(__name__)


class FallbackChain(ContextAwareDiagnosticReporter):
    """Wraps a primary reporter with automatic fallback to CLI-based reporter.

    Implements ContextAwareDiagnosticReporter so it's a drop-in replacement
    wherever reporters are used in the system.
    """

    def __init__(
        self,
        primary: ContextAwareDiagnosticReporter,
        fallback: DiagnosticReporter | None = None,
        hints: list[str] | None = None,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self.status: Literal["active", "degraded", "unavailable"] = "unavailable"
        self.hints: list[str] = hints or []

    @property
    def primary(self) -> ContextAwareDiagnosticReporter:
        return self._primary

    @property
    def name(self) -> str:
        return self._primary.name

    @property
    def supported_extensions(self) -> set[str]:
        return self._primary.supported_extensions

    @property
    def is_running(self) -> bool:
        """True when primary is active or fallback is available (degraded)."""
        return self.status in ("active", "degraded")

    async def start(self) -> None:
        try:
            if hasattr(self._primary, "start"):
                await self._primary.start()  # type: ignore[union-attr]
            self.status = "active"
            logger.info("Started primary reporter: %s", self._primary.name)
        except Exception:
            logger.warning("Primary reporter %s failed to start", self._primary.name, exc_info=True)
            if self._fallback is not None:
                self.status = "degraded"
                logger.info("Falling back to: %s", self._fallback.name)
            else:
                self.status = "unavailable"
                logger.warning("No fallback available for %s", self._primary.name)

    async def stop(self) -> None:
        if hasattr(self._primary, "stop"):
            await self._primary.stop()  # type: ignore[union-attr]

    async def get_diagnostics(self, file_path: Path) -> list[Diagnostic]:
        if self.status == "active":
            try:
                return await self._primary.get_diagnostics(file_path)
            except Exception:
                logger.warning(
                    "Primary %s failed during diagnostics, falling back",
                    self._primary.name,
                    exc_info=True,
                )
                if self._fallback is not None:
                    self.status = "degraded"
                    return await self._fallback.get_diagnostics(file_path)
                self.status = "unavailable"
                return []
        elif self.status == "degraded" and self._fallback is not None:
            return await self._fallback.get_diagnostics(file_path)
        return []

    async def get_all_diagnostics(self) -> dict[Path, list[Diagnostic]]:
        if self.status == "active":
            return await self._primary.get_all_diagnostics()
        elif self.status == "degraded" and self._fallback is not None:
            return await self._fallback.get_all_diagnostics()
        return {}

    async def get_context(self, diagnostic: Diagnostic) -> DiagnosticContext:
        if self.status == "active":
            return await self._primary.get_context(diagnostic)
        return DiagnosticContext(diagnostic=diagnostic)
