"""Search tools: structural pattern search, symbol search, and identifier search."""

from __future__ import annotations

from pathlib import Path

from codebrain.search.pattern import PatternMatch
from codebrain.search.pattern import search_pattern as _search_pattern
from codebrain.search.symbol import IdentifierMatch, SymbolInfo
from codebrain.search.symbol import search_identifiers as _search_identifiers
from codebrain.search.symbol import search_symbol as _search_symbol


async def search_pattern(
    workspace_root: Path,
    pattern: str,
    language: str,
    file_paths: list[Path] | None = None,
    max_results: int = 100,
) -> list[PatternMatch]:
    """Search for structural code patterns using tree-sitter queries."""
    return await _search_pattern(workspace_root, pattern, language, file_paths, max_results)


async def search_symbol(
    workspace_root: Path,
    query: str,
    kind: str | None = None,
    language: str | None = None,
    max_results: int = 100,
) -> list[SymbolInfo]:
    """Search for symbols by name across workspace files."""
    return await _search_symbol(workspace_root, query, kind, language, max_results)


async def search_identifiers(
    workspace_root: Path,
    query: str,
    language: str | None = None,
    max_results: int = 100,
) -> list[IdentifierMatch]:
    """Search for all identifier usages (method calls, variable refs, field access) by name."""
    return await _search_identifiers(workspace_root, query, language, max_results)
