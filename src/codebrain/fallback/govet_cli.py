"""Fallback Go vet CLI reporter when gopls is unavailable."""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

from codebrain.core.interfaces import DiagnosticReporter
from codebrain.core.models import Diagnostic, DiagnosticSeverity, Position, Range

logger = logging.getLogger(__name__)

# go vet output format: file.go:line:col: message  (col is optional)
_GO_VET_LINE_RE = re.compile(r"^(.+\.go):(\d+):(?:(\d+):)?\s*(.+)$")


class GoVetCLIReporter(DiagnosticReporter):
    """Runs `go vet` and parses results. Used in CI or as fallback when gopls is unavailable."""

    DEFAULT_TIMEOUT: float = 30.0

    def __init__(
        self,
        workspace_root: Path,
        go_path: str = "go",
        timeout: float | None = None,
    ) -> None:
        self._workspace_root = workspace_root
        self._go_path = go_path
        self._timeout = timeout or self.DEFAULT_TIMEOUT

    @property
    def name(self) -> str:
        return "govet-cli"

    @property
    def supported_extensions(self) -> set[str]:
        return {".go"}

    async def get_diagnostics(self, file_path: Path) -> list[Diagnostic]:
        results = await self._run_go_vet([str(file_path)])
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
        return await self._run_go_vet(["./..."])

    async def _run_go_vet(self, targets: list[str]) -> dict[Path, list[Diagnostic]]:
        """Run go vet CLI and return parsed diagnostics."""
        cmd = [self._go_path, "vet"] + targets

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
            logger.error("go vet timed out after %.1fs", self._timeout)
            return {}
        except FileNotFoundError:
            logger.error("go not found at: %s", self._go_path)
            return {}
        except Exception:
            logger.exception("Error running go vet")
            return {}

        if stdout:
            logger.debug("go vet stdout: %s", stdout.decode(errors="replace"))

        # go vet writes diagnostics to stderr
        if not stderr:
            return {}

        return self._parse_output(stderr.decode(errors="replace"))

    def _parse_output(self, output: str) -> dict[Path, list[Diagnostic]]:
        """Parse go vet stderr output into Diagnostic objects."""
        results: dict[Path, list[Diagnostic]] = {}

        for line in output.splitlines():
            line = line.strip()
            # Skip package header lines and meta lines
            if not line or line.startswith("#") or line.startswith("vet:"):
                continue

            match = _GO_VET_LINE_RE.match(line)
            if not match:
                continue

            file_str, line_str, col_str, message = match.groups()

            file_path = Path(file_str)
            if not file_path.is_absolute():
                file_path = self._workspace_root / file_path

            # go vet uses 1-indexed lines/cols; convert to 0-indexed
            line_num = max(0, int(line_str) - 1)
            col_num = max(0, int(col_str) - 1) if col_str else 0

            diag = Diagnostic(
                file_path=str(file_path),
                range=Range(
                    start=Position(line=line_num, character=col_num),
                    end=Position(line=line_num, character=col_num),
                ),
                severity=DiagnosticSeverity.WARNING,
                message=message.strip(),
                source="go-vet",
                code=None,
            )
            results.setdefault(file_path, []).append(diag)

        return results
