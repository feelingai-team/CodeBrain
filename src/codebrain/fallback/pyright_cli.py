"""Fallback Pyright CLI reporter when the LSP server is unavailable."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from codebrain.core.interfaces import DiagnosticReporter
from codebrain.core.models import Diagnostic, DiagnosticSeverity, Position, Range

logger = logging.getLogger(__name__)

PYRIGHT_SEVERITY_MAP: dict[str, DiagnosticSeverity] = {
    "error": DiagnosticSeverity.ERROR,
    "warning": DiagnosticSeverity.WARNING,
    "information": DiagnosticSeverity.INFORMATION,
    "hint": DiagnosticSeverity.HINT,
}


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
        results = await self._run_pyright([str(file_path)])
        resolved = file_path.resolve()
        for key in (resolved, file_path, Path(str(file_path))):
            if key in results:
                return results[key]
        # String-based fallback matching
        for key, diags in results.items():
            if str(key).endswith(str(file_path)) or str(file_path).endswith(str(key)):
                return diags
        return []

    async def get_all_diagnostics(self) -> dict[Path, list[Diagnostic]]:
        return await self._run_pyright([str(self._workspace_root)])

    async def _run_pyright(self, targets: list[str]) -> dict[Path, list[Diagnostic]]:
        """Run pyright CLI and return parsed diagnostics."""
        cmd = [self._pyright_path, "--outputjson"]
        if self._config_path is not None:
            cmd.extend(["-p", str(self._config_path)])
        cmd.extend(targets)

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._workspace_root),
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self._timeout
            )
        except TimeoutError:
            logger.error("Pyright timed out after %.1fs", self._timeout)
            return {}
        except FileNotFoundError:
            logger.error("Pyright not found at: %s", self._pyright_path)
            return {}
        except Exception:
            logger.exception("Error running pyright")
            return {}

        if stderr:
            logger.debug("Pyright stderr: %s", stderr.decode(errors="replace"))
        if not stdout:
            return {}

        try:
            output = json.loads(stdout.decode("utf-8"))
        except json.JSONDecodeError:
            logger.error("Failed to parse pyright JSON output")
            return {}

        return self._parse_output(output)

    def _parse_output(self, output: dict[str, Any]) -> dict[Path, list[Diagnostic]]:
        """Parse pyright JSON output into Diagnostic objects."""
        results: dict[Path, list[Diagnostic]] = {}

        for item in output.get("generalDiagnostics", []):
            file_str = item.get("file")
            if not file_str:
                continue

            file_path = Path(file_str)
            if not file_path.is_absolute():
                file_path = self._workspace_root / file_path

            range_data = item.get("range", {})
            start_data = range_data.get("start", {})
            end_data = range_data.get("end", {})

            severity_str = item.get("severity", "error")
            severity = PYRIGHT_SEVERITY_MAP.get(severity_str, DiagnosticSeverity.ERROR)

            diag = Diagnostic(
                file_path=str(file_path),
                range=Range(
                    start=Position(
                        line=start_data.get("line", 0),
                        character=start_data.get("character", 0),
                    ),
                    end=Position(
                        line=end_data.get("line", 0),
                        character=end_data.get("character", 0),
                    ),
                ),
                severity=severity,
                message=item.get("message", ""),
                source="pyright",
                code=item.get("rule"),
            )
            results.setdefault(file_path, []).append(diag)

        return results
