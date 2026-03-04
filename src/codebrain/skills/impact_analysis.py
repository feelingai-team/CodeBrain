"""Skill: analyze the impact of a symbol change across the workspace."""

from __future__ import annotations

from pathlib import Path

from codebrain.core.models import Diagnostic, SignatureChangeImpact
from codebrain.lsp.servers.base import LSPReporter


async def impact_analysis(
    reporter: LSPReporter,
    file_path: Path,
    line: int,
    character: int,
) -> tuple[SignatureChangeImpact, list[Diagnostic]]:
    """Find all usages of a symbol and check for breakage after a change."""
    impact = await reporter.analyze_signature_change_impact(file_path, line, character)
    all_diagnostics: list[Diagnostic] = []
    for affected_file in impact.affected_files:
        diags = await reporter.get_diagnostics(Path(affected_file))
        all_diagnostics.extend(diags)
    return impact, all_diagnostics
