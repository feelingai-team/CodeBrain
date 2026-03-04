"""Navigation tools: definition, references, hover, symbols, call hierarchy, rename."""

from __future__ import annotations

from pathlib import Path

from codebrain.core.interfaces import ContextAwareDiagnosticReporter
from codebrain.core.models import (
    CallHierarchyCall,
    CodeActionSuggestion,
    Diagnostic,
    DocumentSymbol,
    RenameResult,
    SymbolLocation,
)


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


async def document_symbols(
    reporter: ContextAwareDiagnosticReporter,
    file_path: Path,
) -> list[DocumentSymbol]:
    """Get hierarchical symbol outline. Falls back to tree-sitter if LSP unavailable."""
    raise NotImplementedError


async def incoming_calls(
    reporter: ContextAwareDiagnosticReporter,
    file_path: Path,
    line: int,
    character: int,
) -> list[CallHierarchyCall]:
    """Find all callers of a function/method."""
    raise NotImplementedError


async def outgoing_calls(
    reporter: ContextAwareDiagnosticReporter,
    file_path: Path,
    line: int,
    character: int,
) -> list[CallHierarchyCall]:
    """Find all functions called by a function/method."""
    raise NotImplementedError


async def goto_type_definition(
    reporter: ContextAwareDiagnosticReporter,
    file_path: Path,
    line: int,
    character: int,
) -> SymbolLocation | None:
    """Find where the type of a symbol is defined."""
    raise NotImplementedError


async def rename_symbol(
    reporter: ContextAwareDiagnosticReporter,
    file_path: Path,
    line: int,
    character: int,
    new_name: str,
) -> RenameResult:
    """Rename a symbol across the workspace."""
    raise NotImplementedError
