"""Tests for consolidated MCP tool dispatch logic."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codebrain.core.models import (
    Diagnostic,
    DiagnosticContext,
    DiagnosticSeverity,
    DocumentSymbol,
    Position,
    Range,
    SignatureChangeImpact,
    SymbolKind,
    SymbolLocation,
)
from codebrain.mcp.consolidated import (
    check_impact,
    debug_trace,
    explore_symbol,
    outline,
    search,
    validate,
)
from codebrain.search.pattern import PatternMatch
from codebrain.search.symbol import SymbolInfo
from codebrain.skills.signature_check import SignatureCheckResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_ws() -> MagicMock:
    """Create a mock Workspace with common attributes."""
    ws = MagicMock()
    ws.info.root_path = "/workspace"
    ws.reporter = MagicMock()
    ws.reporter.supported_extensions = {".py"}
    ws.index.is_built = False
    return ws


def _make_diag(msg: str = "test error", file_path: str = "/workspace/test.py") -> Diagnostic:
    return Diagnostic(
        file_path=file_path,
        range=Range(start=Position(line=0, character=0), end=Position(line=0, character=5)),
        severity=DiagnosticSeverity.ERROR,
        message=msg,
    )


def _make_ctx(msg: str = "test error") -> DiagnosticContext:
    return DiagnosticContext(
        diagnostic=_make_diag(msg),
        definition=None,
        hover_info=None,
        references=[],
        code_actions=[],
    )


def _make_sym_loc(file_path: str = "/workspace/def.py") -> SymbolLocation:
    return SymbolLocation(
        file_path=file_path,
        range=Range(start=Position(line=10, character=0), end=Position(line=10, character=5)),
    )


# ===========================================================================
# validate
# ===========================================================================
class TestValidate:
    async def test_file_path_uses_contextual_diagnostics(self, mock_ws: MagicMock) -> None:
        ctx = _make_ctx("unused import")
        with patch(
            "codebrain.skills.contextual_diagnostics.contextual_diagnostics",
            new_callable=AsyncMock,
            return_value=[ctx],
        ) as mock_cd:
            result = await validate(mock_ws, file_path="/workspace/main.py")
            mock_cd.assert_awaited_once_with(mock_ws.reporter, Path("/workspace/main.py"))
            assert "unused import" in result

    async def test_directory_uses_validate_workspace(self, mock_ws: MagicMock) -> None:
        with patch(
            "codebrain.tools.validation.validate_workspace",
            new_callable=AsyncMock,
            return_value={Path("/workspace/a.py"): [_make_diag("err1")]},
        ) as mock_vw:
            result = await validate(mock_ws, directory="/workspace")
            mock_vw.assert_awaited_once()
            assert "err1" in result

    async def test_neither_scans_workspace_root(self, mock_ws: MagicMock) -> None:
        with patch(
            "codebrain.tools.validation.validate_workspace",
            new_callable=AsyncMock,
            return_value={},
        ) as mock_vw:
            result = await validate(mock_ws)
            call_args = mock_vw.call_args
            assert call_args[0][1] == Path("/workspace")
            assert "No diagnostics" in result

    async def test_no_diagnostics_returns_message(self, mock_ws: MagicMock) -> None:
        with patch(
            "codebrain.skills.contextual_diagnostics.contextual_diagnostics",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await validate(mock_ws, file_path="/workspace/clean.py")
            assert "No diagnostics" in result


# ===========================================================================
# explore_symbol
# ===========================================================================
class TestExploreSymbol:
    async def test_position_based_gets_definition_and_hover(self, mock_ws: MagicMock) -> None:
        defn = _make_sym_loc()
        with (
            patch(
                "codebrain.tools.navigation.goto_definition",
                new_callable=AsyncMock,
                return_value=defn,
            ),
            patch(
                "codebrain.tools.navigation.get_hover",
                new_callable=AsyncMock,
                return_value="(function) greet(name: str) -> str",
            ),
        ):
            result = await explore_symbol(mock_ws, "/workspace/main.py", line=5, character=4)
            assert "Definition" in result
            assert "greet" in result

    async def test_symbol_query_uses_look_then_jump(self, mock_ws: MagicMock) -> None:
        mock_ws.reporter.get_reporter_for_file.return_value = MagicMock()
        ltj_result = MagicMock()
        ltj_result.matches = [
            MagicMock(name="Greeter", kind="class", definition=_make_sym_loc(), hover_info=None)
        ]
        with patch(
            "codebrain.skills.look_then_jump.look_then_jump",
            new_callable=AsyncMock,
            return_value=ltj_result,
        ):
            result = await explore_symbol(
                mock_ws, "/workspace/main.py", symbol_query="Greeter"
            )
            assert "Greeter" in result

    async def test_no_line_or_query_returns_error(self, mock_ws: MagicMock) -> None:
        result = await explore_symbol(mock_ws, "/workspace/main.py")
        assert "required" in result.lower()

    async def test_include_references(self, mock_ws: MagicMock) -> None:
        with (
            patch(
                "codebrain.tools.navigation.goto_definition",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "codebrain.tools.navigation.get_hover",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "codebrain.tools.navigation.find_references",
                new_callable=AsyncMock,
                return_value=[_make_sym_loc("/workspace/a.py")],
            ),
        ):
            result = await explore_symbol(
                mock_ws, "/workspace/main.py", line=1, character=0,
                include_references=True,
            )
            assert "References" in result

    async def test_no_lsp_for_symbol_query(self, mock_ws: MagicMock) -> None:
        mock_ws.reporter.get_reporter_for_file.return_value = None
        result = await explore_symbol(
            mock_ws, "/workspace/main.py", symbol_query="Greeter"
        )
        assert "No language server" in result


# ===========================================================================
# outline
# ===========================================================================
class TestOutline:
    async def test_file_path_uses_document_symbols(self, mock_ws: MagicMock) -> None:
        syms = [
            DocumentSymbol(
                name="Greeter",
                kind=SymbolKind.CLASS,
                range=Range(
                    start=Position(line=0, character=0), end=Position(line=5, character=0)
                ),
                selection_range=Range(
                    start=Position(line=0, character=6), end=Position(line=0, character=13)
                ),
            )
        ]
        with patch(
            "codebrain.tools.navigation.document_symbols",
            new_callable=AsyncMock,
            return_value=syms,
        ):
            result = await outline(mock_ws, file_path="/workspace/main.py")
            assert "Greeter" in result

    async def test_no_file_uses_repomap_from_index(self, mock_ws: MagicMock) -> None:
        mock_ws.index.is_built = True
        mock_ws.index.generate_repomap.return_value = "# Repository Map\n## main.py"
        result = await outline(mock_ws)
        assert "Repository Map" in result
        mock_ws.index.generate_repomap.assert_called_once_with(4096)

    async def test_no_file_falls_back_to_generate_repomap(self, mock_ws: MagicMock) -> None:
        mock_ws.index.is_built = False
        with patch(
            "codebrain.search.repomap.generate_repomap",
            new_callable=AsyncMock,
            return_value="# Repository Map\nfallback",
        ):
            result = await outline(mock_ws)
            assert "Repository Map" in result


# ===========================================================================
# check_impact
# ===========================================================================
class TestCheckImpact:
    async def test_with_signature_check(self, mock_ws: MagicMock) -> None:
        lsp_r = MagicMock()
        mock_ws.reporter.get_reporter_for_file.return_value = lsp_r
        sig_result = SignatureCheckResult(
            impact=SignatureChangeImpact(
                symbol_name="greet",
                symbol_location=_make_sym_loc(),
                total_usages=3,
                affected_files=["/workspace/a.py"],
            ),
            broken_diagnostics=[],
            hover_info="(method) greet(name: str) -> str",
        )
        with patch(
            "codebrain.skills.signature_check.signature_check",
            new_callable=AsyncMock,
            return_value=sig_result,
        ):
            result = await check_impact(mock_ws, "/workspace/main.py", 5, 4)
            assert "greet" in result
            assert "3" in result
            assert "signature" in result.lower()

    async def test_without_signature_check(self, mock_ws: MagicMock) -> None:
        lsp_r = MagicMock()
        mock_ws.reporter.get_reporter_for_file.return_value = lsp_r
        impact = SignatureChangeImpact(
            symbol_name="helper",
            symbol_location=_make_sym_loc(),
            total_usages=1,
            affected_files=["/workspace/b.py"],
        )
        with patch(
            "codebrain.skills.impact_analysis.impact_analysis",
            new_callable=AsyncMock,
            return_value=(impact, []),
        ):
            result = await check_impact(
                mock_ws, "/workspace/main.py", 10, 0, check_signature=False,
            )
            assert "helper" in result

    async def test_no_language_server(self, mock_ws: MagicMock) -> None:
        mock_ws.reporter.get_reporter_for_file.return_value = None
        result = await check_impact(mock_ws, "/workspace/main.py", 5, 4)
        assert "No language server" in result

    async def test_broken_diagnostics_with_code_actions(self, mock_ws: MagicMock) -> None:
        lsp_r = MagicMock()
        mock_ws.reporter.get_reporter_for_file.return_value = lsp_r
        broken = [_make_diag("type mismatch")]
        sig_result = SignatureCheckResult(
            impact=SignatureChangeImpact(
                symbol_name="greet",
                symbol_location=_make_sym_loc(),
                total_usages=2,
                affected_files=["/workspace/a.py"],
            ),
            broken_diagnostics=broken,
            hover_info=None,
        )
        action = MagicMock(title="Add type cast", is_preferred=True)
        with (
            patch(
                "codebrain.skills.signature_check.signature_check",
                new_callable=AsyncMock,
                return_value=sig_result,
            ),
            patch(
                "codebrain.tools.navigation.get_code_actions",
                new_callable=AsyncMock,
                return_value=[action],
            ),
        ):
            result = await check_impact(mock_ws, "/workspace/main.py", 5, 4)
            assert "type mismatch" in result
            assert "Add type cast" in result
            assert "preferred" in result


# ===========================================================================
# search
# ===========================================================================
class TestSearch:
    async def test_symbol_search(self, mock_ws: MagicMock) -> None:
        syms = [
            SymbolInfo(
                name="Greeter", kind="class", file_path="/workspace/main.py",
                line=0, signature="class Greeter:",
            )
        ]
        with patch(
            "codebrain.tools.search.search_symbol",
            new_callable=AsyncMock,
            return_value=syms,
        ):
            result = await search(mock_ws, "Greeter")
            assert "Greeter" in result
            assert "class" in result

    async def test_pattern_search(self, mock_ws: MagicMock) -> None:
        matches = [
            PatternMatch(
                file_path="/workspace/main.py", start_line=5, end_line=5,
                text="def greet(self):",
            )
        ]
        with patch(
            "codebrain.tools.search.search_pattern",
            new_callable=AsyncMock,
            return_value=matches,
        ):
            result = await search(
                mock_ws, "(function_definition)", language="python", pattern_mode=True,
            )
            assert "greet" in result

    async def test_pattern_mode_requires_language(self, mock_ws: MagicMock) -> None:
        result = await search(mock_ws, "(function_definition)", pattern_mode=True)
        assert "requires" in result.lower()

    async def test_no_results(self, mock_ws: MagicMock) -> None:
        with patch(
            "codebrain.tools.search.search_symbol",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await search(mock_ws, "nonexistent_xyz")
            assert "No symbols" in result


# ===========================================================================
# debug_trace
# ===========================================================================
class TestDebugTrace:
    async def test_parses_and_enriches(self, mock_ws: MagicMock) -> None:
        lsp_r = MagicMock()
        mock_ws.reporter.get_reporter_for_file.return_value = lsp_r

        analysis = MagicMock()
        analysis.frames = [
            MagicMock(
                frame=MagicMock(file_path="/workspace/main.py", line=10, function_name="greet"),
                hover_info="(function) greet()",
                definition=_make_sym_loc(),
            )
        ]
        analysis.root_cause_index = 0
        with patch(
            "codebrain.skills.stack_trace.analyze_stack_trace",
            new_callable=AsyncMock,
            return_value=analysis,
        ):
            result = await debug_trace(mock_ws, "Traceback ...\n  File main.py, line 11")
            assert "greet" in result
            assert "root cause" in result

    async def test_no_language_server(self, mock_ws: MagicMock) -> None:
        mock_ws.reporter.get_reporter_for_file.return_value = None
        result = await debug_trace(mock_ws, "some trace")
        assert "No language server" in result
