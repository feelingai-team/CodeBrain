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
    target_exts = extensions or reporter.supported_extensions
    files: list[Path] = []
    for ext in target_exts:
        files.extend(directory.rglob(f"*{ext}"))
    files = sorted(files)[:max_files]

    results: dict[Path, list[Diagnostic]] = {}
    for file_path in files:
        diags = await reporter.get_diagnostics(file_path)
        if diags:
            results[file_path] = diags
    return results
