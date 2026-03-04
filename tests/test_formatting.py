"""Tests for Markdown formatting utilities."""

from __future__ import annotations

from codebrain.core.formatting import (
    format_call_hierarchy,
    format_diagnostic_context,
    format_diagnostics,
    format_document_symbols,
    format_rename_result,
    format_symbol_locations,
)
from codebrain.core.models import (
    CallHierarchyCall,
    CallHierarchyItem,
    CodeActionSuggestion,
    Diagnostic,
    DiagnosticContext,
    DiagnosticSeverity,
    DocumentSymbol,
    Position,
    Range,
    RenameEdit,
    RenameResult,
    SymbolKind,
    SymbolLocation,
)


def _pos(line: int, char: int) -> Position:
    return Position(line=line, character=char)


def _range(sl: int, sc: int, el: int, ec: int) -> Range:
    return Range(start=_pos(sl, sc), end=_pos(el, ec))


def _diag(
    msg: str,
    severity: DiagnosticSeverity = DiagnosticSeverity.ERROR,
    file_path: str = "test.py",
) -> Diagnostic:
    return Diagnostic(
        file_path=file_path,
        range=_range(0, 0, 0, 10),
        severity=severity,
        message=msg,
        source="pyright",
        code="reportMissing",
    )


class TestFormatDiagnostics:
    def test_empty(self) -> None:
        assert format_diagnostics([]) == "No diagnostics found."

    def test_single_error(self) -> None:
        result = format_diagnostics([_diag("Variable not defined")])
        assert "**ERROR**" in result
        assert "Variable not defined" in result
        assert "[reportMissing]" in result
        assert "(pyright)" in result

    def test_multiple_severities(self) -> None:
        diags = [
            _diag("Error msg", DiagnosticSeverity.ERROR),
            _diag("Warn msg", DiagnosticSeverity.WARNING),
            _diag("Info msg", DiagnosticSeverity.INFORMATION),
        ]
        result = format_diagnostics(diags)
        assert "**ERROR**" in result
        assert "**WARN**" in result
        assert "**INFO**" in result


class TestFormatDiagnosticContext:
    def test_basic_context(self) -> None:
        ctx = DiagnosticContext(diagnostic=_diag("Type mismatch"))
        result = format_diagnostic_context(ctx)
        assert "### ERROR" in result
        assert "Type mismatch" in result

    def test_with_definition(self) -> None:
        ctx = DiagnosticContext(
            diagnostic=_diag("Undefined"),
            definition=SymbolLocation(
                file_path="lib.py", range=_range(10, 0, 10, 5), name="foo"
            ),
        )
        result = format_diagnostic_context(ctx)
        assert "**Definition**" in result
        assert "`foo`" in result

    def test_with_hover_info(self) -> None:
        ctx = DiagnosticContext(
            diagnostic=_diag("Error"),
            hover_info="(variable) x: int",
        )
        result = format_diagnostic_context(ctx)
        assert "**Type info**" in result
        assert "(variable) x: int" in result

    def test_with_code_actions(self) -> None:
        ctx = DiagnosticContext(
            diagnostic=_diag("Missing import"),
            code_actions=[
                CodeActionSuggestion(title="Import os", is_preferred=True),
                CodeActionSuggestion(title="Import sys"),
            ],
        )
        result = format_diagnostic_context(ctx)
        assert "**Suggested fixes**" in result
        assert "Import os" in result
        assert "(preferred)" in result


class TestFormatDocumentSymbols:
    def test_empty(self) -> None:
        assert format_document_symbols([]) == "No symbols found."

    def test_flat_symbols(self) -> None:
        symbols = [
            DocumentSymbol(
                name="foo",
                kind=SymbolKind.FUNCTION,
                range=_range(0, 0, 5, 0),
                selection_range=_range(0, 4, 0, 7),
            ),
            DocumentSymbol(
                name="Bar",
                kind=SymbolKind.CLASS,
                range=_range(7, 0, 20, 0),
                selection_range=_range(7, 6, 7, 9),
            ),
        ]
        result = format_document_symbols(symbols)
        assert "**foo** (function)" in result
        assert "**Bar** (class)" in result

    def test_nested_symbols(self) -> None:
        symbols = [
            DocumentSymbol(
                name="MyClass",
                kind=SymbolKind.CLASS,
                range=_range(0, 0, 10, 0),
                selection_range=_range(0, 6, 0, 13),
                children=[
                    DocumentSymbol(
                        name="method",
                        kind=SymbolKind.METHOD,
                        range=_range(1, 4, 3, 0),
                        selection_range=_range(1, 8, 1, 14),
                    )
                ],
            ),
        ]
        result = format_document_symbols(symbols)
        assert "**MyClass** (class)" in result
        assert "  - **method** (method)" in result


class TestFormatCallHierarchy:
    def test_empty(self) -> None:
        result = format_call_hierarchy([], "incoming")
        assert "No incoming calls found." in result

    def test_with_calls(self) -> None:
        calls = [
            CallHierarchyCall(
                item=CallHierarchyItem(
                    name="caller",
                    kind=SymbolKind.FUNCTION,
                    file_path="main.py",
                    range=_range(5, 0, 10, 0),
                    selection_range=_range(5, 4, 5, 10),
                )
            )
        ]
        result = format_call_hierarchy(calls, "incoming")
        assert "**Incoming calls**" in result
        assert "`caller`" in result
        assert "main.py" in result


class TestFormatRenameResult:
    def test_empty(self) -> None:
        result = format_rename_result(RenameResult())
        assert "No rename edits" in result

    def test_with_edits(self) -> None:
        result = format_rename_result(
            RenameResult(
                edits=[
                    RenameEdit(
                        file_path="a.py", range=_range(0, 0, 0, 3), new_text="bar"
                    ),
                    RenameEdit(
                        file_path="a.py", range=_range(5, 0, 5, 3), new_text="bar"
                    ),
                    RenameEdit(
                        file_path="b.py", range=_range(2, 0, 2, 3), new_text="bar"
                    ),
                ],
                files_affected=2,
            )
        )
        assert "2 files affected" in result
        assert "`a.py`" in result
        assert "`b.py`" in result


class TestFormatSymbolLocations:
    def test_empty(self) -> None:
        assert format_symbol_locations([]) == "No locations found."

    def test_with_locations(self) -> None:
        locs = [
            SymbolLocation(file_path="a.py", range=_range(1, 0, 1, 5), name="foo"),
            SymbolLocation(file_path="b.py", range=_range(3, 0, 3, 5)),
        ]
        result = format_symbol_locations(locs)
        assert "`a.py:" in result
        assert "`foo`" in result
        assert "`b.py:" in result
