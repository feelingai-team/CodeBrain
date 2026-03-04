"""Skill: validate a file and gather full fix context for each diagnostic."""

from __future__ import annotations

from pathlib import Path

from codebrain.core.interfaces import ContextAwareDiagnosticReporter
from codebrain.core.models import DiagnosticContext


async def contextual_diagnostics(
    reporter: ContextAwareDiagnosticReporter,
    file_path: Path,
) -> list[DiagnosticContext]:
    """Validate a file and gather context for each diagnostic."""
    diagnostics = await reporter.get_diagnostics(file_path)
    contexts = []
    for diag in diagnostics:
        ctx = await reporter.get_context(diag)
        contexts.append(ctx)
    return contexts
