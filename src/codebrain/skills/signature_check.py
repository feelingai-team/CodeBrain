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
    raise NotImplementedError
