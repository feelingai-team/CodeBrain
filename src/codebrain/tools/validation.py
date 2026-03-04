"""Validation tools: run LSP diagnostics on files and workspaces."""

from __future__ import annotations

from pathlib import Path

from codebrain.core.interfaces import DiagnosticReporter
from codebrain.core.models import Diagnostic


async def validate_file(
    reporter: DiagnosticReporter,
    file_path: Path,
) -> list[Diagnostic]:
    """Run diagnostics on a single file."""
    return await reporter.get_diagnostics(file_path)


async def validate_workspace(
    reporter: DiagnosticReporter,
    directory: Path,
    extensions: set[str] | None = None,
    max_files: int = 100,
) -> dict[Path, list[Diagnostic]]:
    """Run diagnostics on all matching files in a directory."""
    raise NotImplementedError
