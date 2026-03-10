"""Go language server reporter for Go files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codebrain.core.models import Diagnostic, DiagnosticSeverity, Position, Range
from codebrain.lsp.servers.base import LSPReporter

# Patterns in gopls diagnostics that indicate missing module dependencies
_MISSING_MODULE_PATTERNS = (
    "could not import",
    "cannot find package",
    "no required module provides package",
)


class GoplsReporter(LSPReporter):
    """Diagnostic reporter using gopls for Go files."""

    _project_markers = ("go.mod", "go.work")

    def __init__(
        self,
        workspace_root: Path,
        server_command: list[str] | None = None,
    ) -> None:
        command = server_command or ["gopls", "serve"]
        super().__init__(workspace_root, command, "go")

    def _build_subprocess_env(self, effective_root: Path) -> dict[str, str] | None:
        """Ensure gopls runs in Go modules mode with correct env vars."""
        import os
        import shutil

        env: dict[str, str] = {"GO111MODULE": "on"}

        gomodcache = os.environ.get("GOMODCACHE")
        if gomodcache:
            env["GOMODCACHE"] = gomodcache

        goroot = os.environ.get("GOROOT")
        if not goroot:
            go_bin = shutil.which("go")
            if go_bin:
                import subprocess

                try:
                    result = subprocess.run(
                        [go_bin, "env", "GOROOT"],
                        capture_output=True, text=True, timeout=5,
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        goroot = result.stdout.strip()
                except Exception:
                    pass

        if goroot:
            env["GOROOT"] = goroot

        return env

    def _build_initialization_options(
        self, effective_root: Path,
    ) -> dict[str, Any] | None:
        """Configure gopls build settings for module-aware mode."""
        return {
            "build": {
                "env": {"GO111MODULE": "on"},
            },
        }

    @property
    def name(self) -> str:
        return "gopls"

    @property
    def supported_extensions(self) -> set[str]:
        return {".go"}

    async def get_diagnostics(self, file_path: Path) -> list[Diagnostic]:
        """Get diagnostics, adding actionable hints for missing module errors."""
        diagnostics = await super().get_diagnostics(file_path)

        has_missing_modules = any(
            any(pat in d.message.lower() for pat in _MISSING_MODULE_PATTERNS)
            for d in diagnostics
        )

        if has_missing_modules:
            effective_root = self._resolve_project_root()
            hint = Diagnostic(
                file_path=str(file_path),
                range=Range(
                    start=Position(line=0, character=0),
                    end=Position(line=0, character=0),
                ),
                severity=DiagnosticSeverity.HINT,
                message=(
                    "Some imports could not be resolved — Go module dependencies "
                    "may not be downloaded. Run `go mod download` in "
                    f"`{effective_root}` to fetch them."
                ),
                source="codebrain",
                code="MissingModules",
            )
            diagnostics = [hint] + diagnostics

        return diagnostics
