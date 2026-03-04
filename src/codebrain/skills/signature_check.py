"""Skill: detect signature changes and their downstream impact."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from codebrain.core.models import Diagnostic, SignatureChangeImpact
from codebrain.lsp.servers.base import LSPReporter


@dataclass
class SignatureCheckResult:
    """Result of a signature change check."""

    impact: SignatureChangeImpact
    broken_diagnostics: list[Diagnostic]
    hover_info: str | None


async def signature_check(
    reporter: LSPReporter,
    file_path: Path,
    line: int,
    character: int,
) -> SignatureCheckResult:
    """Detect signature changes and check their downstream impact."""
    impact = await reporter.analyze_signature_change_impact(file_path, line, character)

    # Gather diagnostics from affected files to find broken usages
    broken: list[Diagnostic] = []
    for affected_file in impact.affected_files:
        diags = await reporter.get_diagnostics(Path(affected_file))
        broken.extend(diags)

    # Get hover info for the current signature
    hover_info: str | None = None
    if reporter._client is not None:
        try:
            hover = await reporter._client.get_hover(file_path, line, character)
            if hover is not None:
                from lsprotocol import types as lsp

                if isinstance(hover.contents, str):
                    hover_info = hover.contents
                elif isinstance(hover.contents, lsp.MarkupContent):
                    hover_info = hover.contents.value
        except Exception:
            pass

    return SignatureCheckResult(
        impact=impact,
        broken_diagnostics=broken,
        hover_info=hover_info,
    )
