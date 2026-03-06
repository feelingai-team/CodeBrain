"""Navigation tools: definition, references, hover, symbols, call hierarchy, rename."""

from __future__ import annotations

from pathlib import Path

from lsprotocol import types as lsp

from codebrain.core.interfaces import ContextAwareDiagnosticReporter
from codebrain.core.models import (
    CallHierarchyCall,
    CallHierarchyItem,
    CodeActionSuggestion,
    Diagnostic,
    DocumentSymbol,
    RenameEdit,
    RenameResult,
    SymbolKind,
    SymbolLocation,
)
from codebrain.lsp.servers.base import LSPReporter, lsp_range_to_range, uri_to_path


def _get_lsp_reporter(
    reporter: ContextAwareDiagnosticReporter,
    file_path: Path | None = None,
) -> LSPReporter:
    """Resolve to an LSPReporter, handling MultiLanguageReporter routing."""
    if isinstance(reporter, LSPReporter):
        return reporter

    # Handle MultiLanguageReporter by routing to the correct sub-reporter
    from codebrain.lsp.servers.multi import MultiLanguageReporter

    if isinstance(reporter, MultiLanguageReporter) and file_path is not None:
        sub = reporter.get_reporter_for_file(file_path)
        if sub is not None:
            return sub

    msg = f"Navigation tools require an LSPReporter, got {type(reporter).__name__}"
    raise TypeError(msg)


async def goto_definition(
    reporter: ContextAwareDiagnosticReporter,
    file_path: Path,
    line: int,
    character: int,
) -> SymbolLocation | None:
    """Find where a symbol is defined."""
    lsp_reporter = _get_lsp_reporter(reporter, file_path)
    await lsp_reporter.open_file(file_path)
    return await lsp_reporter._resolve_definition(file_path, line, character)


async def find_references(
    reporter: ContextAwareDiagnosticReporter,
    file_path: Path,
    line: int,
    character: int,
) -> list[SymbolLocation]:
    """Find all references to a symbol."""
    lsp_reporter = _get_lsp_reporter(reporter, file_path)
    await lsp_reporter.open_file(file_path)
    refs, _ = await lsp_reporter._gather_recursive_references(
        file_path, line, character, max_depth=1, max_refs=50
    )
    return refs


async def get_hover(
    reporter: ContextAwareDiagnosticReporter,
    file_path: Path,
    line: int,
    character: int,
) -> str | None:
    """Get type/documentation info for a symbol at a position."""
    lsp_reporter = _get_lsp_reporter(reporter, file_path)
    await lsp_reporter.open_file(file_path)
    assert lsp_reporter._client is not None
    hover = await lsp_reporter._client.get_hover(file_path, line, character)
    if hover is None:
        return None
    contents = hover.contents
    if isinstance(contents, str):
        return contents
    if isinstance(contents, lsp.MarkupContent):
        return contents.value
    return None


async def get_code_actions(
    reporter: ContextAwareDiagnosticReporter,
    diagnostic: Diagnostic,
) -> list[CodeActionSuggestion]:
    """Get suggested fixes for a diagnostic."""
    lsp_reporter = _get_lsp_reporter(reporter, Path(diagnostic.file_path))
    return await lsp_reporter.get_code_actions_for_diagnostic(diagnostic)


async def document_symbols(
    reporter: ContextAwareDiagnosticReporter,
    file_path: Path,
) -> list[DocumentSymbol]:
    """Get hierarchical symbol outline. Falls back to tree-sitter if LSP unavailable."""
    lsp_reporter = _get_lsp_reporter(reporter, file_path)
    await lsp_reporter.open_file(file_path)
    assert lsp_reporter._client is not None

    lsp_symbols = await lsp_reporter._client.get_document_symbols(file_path)
    if lsp_symbols is None:
        # Fallback to tree-sitter
        from codebrain.search.symbols import get_document_symbols as ts_get_symbols

        return await ts_get_symbols(file_path)

    return [_convert_document_symbol(s) for s in lsp_symbols]


def _convert_document_symbol(
    sym: lsp.DocumentSymbol | lsp.SymbolInformation,
) -> DocumentSymbol:
    """Convert an LSP DocumentSymbol/SymbolInformation to our model."""
    if isinstance(sym, lsp.DocumentSymbol):
        children = [_convert_document_symbol(c) for c in (sym.children or [])]
        return DocumentSymbol(
            name=sym.name,
            kind=SymbolKind(sym.kind.value),
            range=lsp_range_to_range(sym.range),
            selection_range=lsp_range_to_range(sym.selection_range),
            detail=sym.detail,
            children=children,
        )
    # SymbolInformation (flat, no children)
    return DocumentSymbol(
        name=sym.name,
        kind=SymbolKind(sym.kind.value),
        range=lsp_range_to_range(sym.location.range),
        selection_range=lsp_range_to_range(sym.location.range),
    )


def _convert_call_hierarchy(
    call: lsp.CallHierarchyIncomingCall | lsp.CallHierarchyOutgoingCall,
) -> CallHierarchyCall:
    """Convert an LSP CallHierarchyCall to our model."""
    if isinstance(call, lsp.CallHierarchyIncomingCall):
        item = call.from_
        from_ranges = [lsp_range_to_range(r) for r in call.from_ranges]
    else:
        item = call.to
        from_ranges = [lsp_range_to_range(r) for r in call.from_ranges]

    return CallHierarchyCall(
        item=CallHierarchyItem(
            name=item.name,
            kind=SymbolKind(item.kind.value),
            file_path=str(uri_to_path(item.uri)),
            range=lsp_range_to_range(item.range),
            selection_range=lsp_range_to_range(item.selection_range),
            detail=item.detail,
        ),
        from_ranges=from_ranges,
    )


async def incoming_calls(
    reporter: ContextAwareDiagnosticReporter,
    file_path: Path,
    line: int,
    character: int,
) -> list[CallHierarchyCall]:
    """Find all callers of a function/method."""
    lsp_reporter = _get_lsp_reporter(reporter, file_path)
    await lsp_reporter.open_file(file_path)
    assert lsp_reporter._client is not None
    result = await lsp_reporter._client.get_call_hierarchy_incoming(
        file_path, line, character
    )
    return [_convert_call_hierarchy(c) for c in result]


async def outgoing_calls(
    reporter: ContextAwareDiagnosticReporter,
    file_path: Path,
    line: int,
    character: int,
) -> list[CallHierarchyCall]:
    """Find all functions called by a function/method."""
    lsp_reporter = _get_lsp_reporter(reporter, file_path)
    await lsp_reporter.open_file(file_path)
    assert lsp_reporter._client is not None
    result = await lsp_reporter._client.get_call_hierarchy_outgoing(
        file_path, line, character
    )
    return [_convert_call_hierarchy(c) for c in result]


async def goto_type_definition(
    reporter: ContextAwareDiagnosticReporter,
    file_path: Path,
    line: int,
    character: int,
) -> SymbolLocation | None:
    """Find where the type of a symbol is defined."""
    lsp_reporter = _get_lsp_reporter(reporter, file_path)
    await lsp_reporter.open_file(file_path)
    assert lsp_reporter._client is not None
    result = await lsp_reporter._client.get_type_definition(file_path, line, character)
    if not result:
        return None
    first = result[0]
    if isinstance(first, lsp.LocationLink):
        return SymbolLocation(
            file_path=str(uri_to_path(first.target_uri)),
            range=lsp_range_to_range(first.target_range),
        )
    if isinstance(first, lsp.Location):
        return SymbolLocation(
            file_path=str(uri_to_path(first.uri)),
            range=lsp_range_to_range(first.range),
        )
    return None


async def rename_symbol(
    reporter: ContextAwareDiagnosticReporter,
    file_path: Path,
    line: int,
    character: int,
    new_name: str,
) -> RenameResult:
    """Rename a symbol across the workspace."""
    lsp_reporter = _get_lsp_reporter(reporter, file_path)
    await lsp_reporter.open_file(file_path)
    assert lsp_reporter._client is not None
    workspace_edit = await lsp_reporter._client.rename(file_path, line, character, new_name)
    if workspace_edit is None:
        return RenameResult()

    edits: list[RenameEdit] = []
    affected_files: set[str] = set()

    if workspace_edit.changes:
        for uri, text_edits in workspace_edit.changes.items():
            edit_path = str(uri_to_path(uri))
            affected_files.add(edit_path)
            for te in text_edits:
                edits.append(
                    RenameEdit(
                        file_path=edit_path,
                        range=lsp_range_to_range(te.range),
                        new_text=te.new_text,
                    )
                )

    if workspace_edit.document_changes:
        for change in workspace_edit.document_changes:
            if isinstance(change, lsp.TextDocumentEdit):
                edit_path = str(uri_to_path(change.text_document.uri))
                affected_files.add(edit_path)
                for te in change.edits:
                    if isinstance(te, lsp.SnippetTextEdit):
                        # SnippetTextEdit uses 'snippet' not 'new_text'
                        continue
                    edits.append(
                        RenameEdit(
                            file_path=edit_path,
                            range=lsp_range_to_range(te.range),
                            new_text=te.new_text,
                        )
                    )

    return RenameResult(edits=edits, files_affected=len(affected_files))
