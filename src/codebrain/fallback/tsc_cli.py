"""Fallback tsc CLI reporter when typescript-language-server is unavailable."""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

from codebrain.core.interfaces import DiagnosticReporter
from codebrain.core.models import Diagnostic, DiagnosticSeverity, Position, Range

logger = logging.getLogger(__name__)

# tsc --pretty false output format: file.ts(line,col): error|warning TSxxxx: message
_TSC_LINE_RE = re.compile(r"^(.+?)\((\d+),(\d+)\):\s*(error|warning)\s+(TS\d+):\s*(.+)$")

_TSC_SEVERITY_MAP: dict[str, DiagnosticSeverity] = {
    "error": DiagnosticSeverity.ERROR,
    "warning": DiagnosticSeverity.WARNING,
}


class TscCLIReporter(DiagnosticReporter):
    """Runs `tsc --noEmit` and parses results. Used in CI or as fallback when
    typescript-language-server is unavailable."""

    DEFAULT_TIMEOUT: float = 30.0

    def __init__(
        self,
        workspace_root: Path,
        tsc_path: str = "tsc",
        tsconfig_path: Path | None = None,
        timeout: float | None = None,
    ) -> None:
        self._workspace_root = workspace_root
        self._tsc_path = tsc_path
        self._tsconfig_path = tsconfig_path
        self._timeout = timeout or self.DEFAULT_TIMEOUT

    @property
    def name(self) -> str:
        return "tsc-cli"

    @property
    def supported_extensions(self) -> set[str]:
        return {".ts", ".tsx", ".js", ".jsx"}

    async def get_diagnostics(self, file_path: Path) -> list[Diagnostic]:
        # tsc runs on the whole project; filter results to the requested file
        results = await self._run_tsc()
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
        return await self._run_tsc()

    async def _run_tsc(self) -> dict[Path, list[Diagnostic]]:
        """Run tsc --noEmit CLI and return parsed diagnostics."""
        cmd = [self._tsc_path, "--noEmit", "--pretty", "false"]
        if self._tsconfig_path is not None:
            cmd.extend(["-p", str(self._tsconfig_path)])

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
            logger.error("tsc timed out after %.1fs", self._timeout)
            return {}
        except FileNotFoundError:
            logger.error("tsc not found at: %s", self._tsc_path)
            return {}
        except Exception:
            logger.exception("Error running tsc")
            return {}

        if stderr:
            logger.debug("tsc stderr: %s", stderr.decode(errors="replace"))

        # tsc writes diagnostics to stdout
        if not stdout:
            return {}

        return self._parse_output(stdout.decode(errors="replace"))

    def _parse_output(self, output: str) -> dict[Path, list[Diagnostic]]:
        """Parse tsc stdout output into Diagnostic objects."""
        results: dict[Path, list[Diagnostic]] = {}

        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue

            match = _TSC_LINE_RE.match(line)
            if not match:
                continue

            file_str, line_str, col_str, severity_str, code_str, message = match.groups()

            file_path = Path(file_str)
            if not file_path.is_absolute():
                file_path = self._workspace_root / file_path

            # tsc uses 1-indexed lines/cols; convert to 0-indexed
            line_num = max(0, int(line_str) - 1)
            col_num = max(0, int(col_str) - 1)

            severity = _TSC_SEVERITY_MAP.get(severity_str, DiagnosticSeverity.ERROR)

            diag = Diagnostic(
                file_path=str(file_path),
                range=Range(
                    start=Position(line=line_num, character=col_num),
                    end=Position(line=line_num, character=col_num),
                ),
                severity=severity,
                message=message.strip(),
                source="tsc",
                code=code_str,
            )
            results.setdefault(file_path, []).append(diag)

        return results
