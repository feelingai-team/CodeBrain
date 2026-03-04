"""Navigation tools: definition, references, hover, code actions."""

from __future__ import annotations

from pathlib import Path

from codebrain.core.interfaces import ContextAwareDiagnosticReporter
from codebrain.core.models import CodeActionSuggestion, Diagnostic, SymbolLocation


async def goto_definition(
    reporter: ContextAwareDiagnosticReporter,
    file_path: Path,
    line: int,
    character: int,
) -> SymbolLocation | None:
    """Find where a symbol is defined."""
    raise NotImplementedError


async def find_references(
    reporter: ContextAwareDiagnosticReporter,
    file_path: Path,
    line: int,
    character: int,
) -> list[SymbolLocation]:
    """Find all references to a symbol."""
    raise NotImplementedError


async def get_hover(
    reporter: ContextAwareDiagnosticReporter,
    file_path: Path,
    line: int,
    character: int,
) -> str | None:
    """Get type/documentation info for a symbol at a position."""
    raise NotImplementedError


async def get_code_actions(
    reporter: ContextAwareDiagnosticReporter,
    diagnostic: Diagnostic,
) -> list[CodeActionSuggestion]:
    """Get suggested fixes for a diagnostic."""
    raise NotImplementedError
