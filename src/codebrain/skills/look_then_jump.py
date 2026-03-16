"""Skill: Look-Then-Jump — outline a file, find a symbol, jump to its definition."""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

from codebrain.core.models import DocumentSymbol, SymbolLocation
from codebrain.lsp.servers.base import LSPReporter


@dataclass
class SymbolJumpResult:
    """Result for a single matched symbol."""

    name: str
    kind: str
    definition: SymbolLocation | None
    hover_info: str | None


@dataclass
class LookThenJumpResult:
    """Full result of the look-then-jump workflow."""

    file_path: str
    query: str
    outline: list[DocumentSymbol]
    matches: list[SymbolJumpResult]


def _flatten_symbols(symbols: list[DocumentSymbol]) -> list[DocumentSymbol]:
    """Flatten a hierarchical symbol list into a flat list."""
    result: list[DocumentSymbol] = []
    stack = list(reversed(symbols))
    while stack:
        sym = stack.pop()
        result.append(sym)
        if sym.children:
            stack.extend(reversed(sym.children))
    return result


def _matches_query(name: str, query: str) -> bool:
    """Match a symbol name against a query (case-insensitive, supports globs)."""
    if any(c in query for c in "*?["):
        return fnmatch(name.lower(), query.lower())
    return query.lower() in name.lower()


async def look_then_jump(
    reporter: LSPReporter,
    file_path: Path,
    symbol_query: str,
) -> LookThenJumpResult:
    """Two-step Look-Then-Jump workflow.

    1. **Look**: Get the file's symbol outline (without reading full content).
    2. **Match**: Find symbols matching the query.
    3. **Jump**: For each match, resolve definition + hover info.
    """
    from codebrain.tools.navigation import document_symbols, get_hover, goto_definition

    # Step 1: Look — get outline
    outline = await document_symbols(reporter, file_path)
    flat = _flatten_symbols(outline)

    # Step 2: Match — if LSP symbols don't contain the query, retry with tree-sitter
    # (LSP servers like Pyright omit private/underscore symbols from documentSymbol)
    matched = [sym for sym in flat if _matches_query(sym.name, symbol_query)]
    if not matched and symbol_query:
        from codebrain.search.symbols import get_document_symbols as ts_get_symbols

        ts_outline = await ts_get_symbols(file_path)
        ts_flat = _flatten_symbols(ts_outline)
        matched = [sym for sym in ts_flat if _matches_query(sym.name, symbol_query)]
        if matched:
            outline = ts_outline

    # Step 3: Jump — resolve each match
    results: list[SymbolJumpResult] = []
    for sym in matched:
        line = sym.selection_range.start.line
        char = sym.selection_range.start.character

        defn = await goto_definition(reporter, file_path, line, char)
        hover = await get_hover(reporter, file_path, line, char)

        results.append(
            SymbolJumpResult(
                name=sym.name,
                kind=sym.kind.name.lower(),
                definition=defn,
                hover_info=hover,
            )
        )

    return LookThenJumpResult(
        file_path=str(file_path),
        query=symbol_query,
        outline=outline,
        matches=results,
    )
