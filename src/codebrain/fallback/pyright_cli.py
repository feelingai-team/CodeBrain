"""Fallback Pyright CLI reporter when the LSP server is unavailable."""

from __future__ import annotations

from pathlib import Path

from codebrain.core.interfaces import DiagnosticReporter
from codebrain.core.models import Diagnostic


class PyrightCLIReporter(DiagnosticReporter):
    """Runs `pyright --outputjson` and parses results. Used in CI or as fallback."""

    DEFAULT_TIMEOUT: float = 15.0

    def __init__(
        self,
        workspace_root: Path,
        pyright_path: str = "pyright",
        config_path: Path | None = None,
        timeout: float | None = None,
    ) -> None:
        self._workspace_root = workspace_root
        self._pyright_path = pyright_path
        self._config_path = config_path
        self._timeout = timeout or self.DEFAULT_TIMEOUT

    @property
    def name(self) -> str:
        return "pyright-cli"

    @property
    def supported_extensions(self) -> set[str]:
        return {".py", ".pyi"}

    async def get_diagnostics(self, file_path: Path) -> list[Diagnostic]:
        raise NotImplementedError

    async def get_all_diagnostics(self) -> dict[Path, list[Diagnostic]]:
        raise NotImplementedError
