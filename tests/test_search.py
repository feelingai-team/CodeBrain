"""Tests for tree-sitter based search functionality."""

from __future__ import annotations

from pathlib import Path

import pytest

from codebrain.core.models import SymbolKind
from codebrain.search.parser import (
    EXTENSION_TO_LANGUAGE,
    TreeSitterParser,
    language_for_extension,
)
from codebrain.search.pattern import search_pattern
from codebrain.search.symbol import search_identifiers, search_symbol
from codebrain.search.symbols import get_document_symbols

SAMPLE_PYTHON = """\
class Greeter:
    def greet(self, name: str) -> str:
        return "Hello, " + name

def add(a: int, b: int) -> int:
    return a + b

PI = 3.14
"""


@pytest.fixture
def py_workspace(tmp_path: Path) -> Path:
    """Create a workspace with a sample Python file."""
    (tmp_path / "sample.py").write_text(SAMPLE_PYTHON)
    return tmp_path


@pytest.fixture
def ts_parser() -> TreeSitterParser:
    return TreeSitterParser()


# --- Parser tests ---


class TestTreeSitterParser:
    def test_loads_python_grammar(self, ts_parser: TreeSitterParser) -> None:
        lang = ts_parser.get_language("python")
        assert lang is not None

    def test_caches_across_calls(self, ts_parser: TreeSitterParser) -> None:
        lang1 = ts_parser.get_language("python")
        lang2 = ts_parser.get_language("python")
        assert lang1 is lang2

    def test_caches_parser(self, ts_parser: TreeSitterParser) -> None:
        p1 = ts_parser.get_parser("python")
        p2 = ts_parser.get_parser("python")
        assert p1 is p2

    def test_parse_python_source(self, ts_parser: TreeSitterParser) -> None:
        tree = ts_parser.parse(b"def hello(): pass", "python")
        assert tree.root_node.type == "module"

    def test_parse_file(self, py_workspace: Path, ts_parser: TreeSitterParser) -> None:
        tree = ts_parser.parse_file(py_workspace / "sample.py")
        assert tree.root_node.type == "module"

    def test_unsupported_language(self, ts_parser: TreeSitterParser) -> None:
        with pytest.raises(ValueError, match="Unsupported language"):
            ts_parser.get_language("cobol")

    def test_unsupported_extension(self, ts_parser: TreeSitterParser) -> None:
        tmp = Path("/tmp/test.cobol")
        with pytest.raises(ValueError, match="Cannot determine language"):
            ts_parser.parse_file(tmp)


# --- Extension mapping tests ---


class TestExtensionMapping:
    def test_python_extensions(self) -> None:
        assert language_for_extension(".py") == "python"
        assert language_for_extension(".pyi") == "python"

    def test_typescript_extensions(self) -> None:
        assert language_for_extension(".ts") == "typescript"
        assert language_for_extension(".tsx") == "typescript"

    def test_cpp_extensions(self) -> None:
        assert language_for_extension(".cpp") == "cpp"
        assert language_for_extension(".hpp") == "cpp"

    def test_unknown_extension(self) -> None:
        assert language_for_extension(".rs") is None

    def test_all_extensions_have_valid_languages(self) -> None:
        for ext, lang in EXTENSION_TO_LANGUAGE.items():
            assert lang in ("python", "javascript", "typescript", "c", "cpp", "go"), (
                f"Unknown language {lang} for {ext}"
            )


# --- Pattern search tests ---


class TestPatternSearch:
    async def test_search_function_definitions(self, py_workspace: Path) -> None:
        results = await search_pattern(
            py_workspace,
            "(function_definition name: (identifier) @name)",
            "python",
        )
        names = [m.captures.get("name", "") for m in results]
        assert "greet" in names
        assert "add" in names

    async def test_search_class_definitions(self, py_workspace: Path) -> None:
        results = await search_pattern(
            py_workspace,
            "(class_definition name: (identifier) @name)",
            "python",
        )
        names = [m.captures.get("name", "") for m in results]
        assert "Greeter" in names

    async def test_search_with_max_results(self, py_workspace: Path) -> None:
        results = await search_pattern(
            py_workspace,
            "(function_definition name: (identifier) @name)",
            "python",
            max_results=1,
        )
        assert len(results) == 1

    async def test_search_specific_files(self, py_workspace: Path) -> None:
        results = await search_pattern(
            py_workspace,
            "(function_definition name: (identifier) @name)",
            "python",
            file_paths=[py_workspace / "sample.py"],
        )
        assert len(results) >= 1

    async def test_search_no_matches(self, py_workspace: Path) -> None:
        results = await search_pattern(
            py_workspace,
            "(while_statement) @loop",
            "python",
        )
        assert results == []


# --- Symbol search tests ---


class TestSymbolSearch:
    async def test_search_by_name(self, py_workspace: Path) -> None:
        results = await search_symbol(py_workspace, "add")
        assert any(s.name == "add" for s in results)

    async def test_search_by_kind(self, py_workspace: Path) -> None:
        results = await search_symbol(py_workspace, "*", kind="class")
        assert any(s.name == "Greeter" and s.kind == "class" for s in results)

    async def test_search_glob_pattern(self, py_workspace: Path) -> None:
        results = await search_symbol(py_workspace, "Greet*")
        assert any(s.name == "Greeter" for s in results)

    async def test_search_case_insensitive(self, py_workspace: Path) -> None:
        results = await search_symbol(py_workspace, "ADD")
        assert any(s.name == "add" for s in results)

    async def test_search_with_language_filter(self, py_workspace: Path) -> None:
        results = await search_symbol(py_workspace, "*", language="python")
        assert len(results) >= 1

    async def test_symbol_has_signature(self, py_workspace: Path) -> None:
        results = await search_symbol(py_workspace, "add")
        add_sym = next(s for s in results if s.name == "add")
        assert add_sym.signature is not None
        assert "def add" in add_sym.signature

    async def test_multi_keyword_query(self, tmp_path: Path) -> None:
        (tmp_path / "handlers.py").write_text(
            "class MotionHandler:\n    pass\n\n"
            "class MotionPreview:\n    pass\n\n"
            "def handle_motion_data():\n    pass\n\n"
            "def unrelated_func():\n    pass\n"
        )
        # "motion handler" — both keywords must appear in name
        results = await search_symbol(tmp_path, "motion handler")
        names = [s.name for s in results]
        assert "MotionHandler" in names  # contains both "motion" and "handler"
        assert "MotionPreview" not in names  # missing "handler"
        assert "unrelated_func" not in names

        # "motion data" — matches handle_motion_data
        results2 = await search_symbol(tmp_path, "motion data")
        names2 = [s.name for s in results2]
        assert "handle_motion_data" in names2

    async def test_multi_keyword_all_must_match(self, tmp_path: Path) -> None:
        (tmp_path / "api.py").write_text(
            "def get_motion_preview():\n    pass\n\n"
            "def get_status():\n    pass\n"
        )
        results = await search_symbol(tmp_path, "motion preview")
        names = [s.name for s in results]
        assert "get_motion_preview" in names
        assert "get_status" not in names

    async def test_exact_match_ranks_higher(self, tmp_path: Path) -> None:
        (tmp_path / "models.py").write_text(
            "class MotionDataHandler:\n    pass\n\n"
            "class Motion:\n    pass\n"
        )
        results = await search_symbol(tmp_path, "Motion")
        # Exact match "Motion" should come before substring match "MotionDataHandler"
        assert results[0].name == "Motion"

    async def test_single_keyword_still_works(self, py_workspace: Path) -> None:
        results = await search_symbol(py_workspace, "greet")
        assert any(s.name == "greet" for s in results)

    async def test_pipe_or_query(self, tmp_path: Path) -> None:
        (tmp_path / "parsers.py").write_text(
            "class StreamParser:\n    pass\n\n"
            "class FrameParser:\n    pass\n\n"
            "class Validator:\n    pass\n"
        )
        results = await search_symbol(tmp_path, "StreamParser|FrameParser")
        names = [s.name for s in results]
        assert "StreamParser" in names
        assert "FrameParser" in names
        assert "Validator" not in names

    async def test_pipe_or_with_keywords(self, tmp_path: Path) -> None:
        (tmp_path / "handlers.py").write_text(
            "class MotionHandler:\n    pass\n\n"
            "class FrameParser:\n    pass\n\n"
            "def unrelated():\n    pass\n"
        )
        # Mix: first alt is multi-keyword, second is exact
        results = await search_symbol(tmp_path, "motion handler|FrameParser")
        names = [s.name for s in results]
        assert "MotionHandler" in names
        assert "FrameParser" in names
        assert "unrelated" not in names

    async def test_pipe_or_best_score_wins(self, tmp_path: Path) -> None:
        (tmp_path / "models.py").write_text(
            "class StreamParser:\n    pass\n\n"
            "class StreamValidator:\n    pass\n"
        )
        # "StreamParser" is exact for first, "StreamValidator" only matches via substring "Stream"
        results = await search_symbol(tmp_path, "StreamParser|Stream")
        # StreamParser (exact=100) should rank above StreamValidator (substr=80)
        assert results[0].name == "StreamParser"


# --- Document symbols tests ---


class TestDocumentSymbols:
    async def test_hierarchical_python(self, py_workspace: Path) -> None:
        symbols = await get_document_symbols(py_workspace / "sample.py")
        names = [s.name for s in symbols]
        assert "Greeter" in names
        assert "add" in names

    async def test_class_has_method_children(self, py_workspace: Path) -> None:
        symbols = await get_document_symbols(py_workspace / "sample.py")
        greeter = next(s for s in symbols if s.name == "Greeter")
        assert greeter.kind == SymbolKind.CLASS
        child_names = [c.name for c in greeter.children]
        assert "greet" in child_names

    async def test_function_kind(self, py_workspace: Path) -> None:
        symbols = await get_document_symbols(py_workspace / "sample.py")
        add_sym = next(s for s in symbols if s.name == "add")
        assert add_sym.kind == SymbolKind.FUNCTION

    async def test_unknown_extension_returns_empty(self, tmp_path: Path) -> None:
        unknown = tmp_path / "test.rs"
        unknown.write_text("fn main() {}")
        symbols = await get_document_symbols(unknown)
        assert symbols == []

    async def test_symbol_ranges(self, py_workspace: Path) -> None:
        symbols = await get_document_symbols(py_workspace / "sample.py")
        greeter = next(s for s in symbols if s.name == "Greeter")
        assert greeter.range.start.line == 0
        assert greeter.selection_range.start.line == 0


# --- Identifier search tests ---


SAMPLE_GO = """\
package main

import "fmt"

func handleRequest(db *Database) {
    offset := db.Offset(10)
    limit := db.Limit(20)
    results := db.Query().Order("created_at")
    fmt.Println(results, offset, limit)
}
"""

SAMPLE_PYTHON_IDENTS = """\
class ApiService:
    def get_items(self, offset: int, limit: int):
        return self.db.query().offset(offset).limit(limit)

def process(service: ApiService):
    items = service.get_items(offset=0, limit=50)
    return items
"""


class TestIdentifierSearch:
    async def test_finds_method_calls(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text(SAMPLE_PYTHON_IDENTS)
        results = await search_identifiers(tmp_path, "offset", language="python")
        assert len(results) > 0
        # Should find usages, not just the definition
        assert any(r.name == "offset" for r in results)

    async def test_pipe_or_query(self, tmp_path: Path) -> None:
        # Use separate files so identifiers are on distinct lines
        (tmp_path / "a.py").write_text("def get_offset():\n    return offset_val\n")
        (tmp_path / "b.py").write_text("def get_limit():\n    return limit_val\n")
        results = await search_identifiers(tmp_path, "offset|limit", language="python")
        names = {r.name for r in results}
        # pipe OR should match both alternatives
        assert "offset_val" in names or "get_offset" in names
        assert "limit_val" in names or "get_limit" in names

    async def test_deduplicates_same_line(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text(SAMPLE_PYTHON_IDENTS)
        results = await search_identifiers(tmp_path, "offset", language="python")
        # Each line should appear at most once
        lines = [r.line for r in results]
        assert len(lines) == len(set(lines))

    async def test_max_results(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text(SAMPLE_PYTHON_IDENTS)
        results = await search_identifiers(tmp_path, "offset|limit", max_results=2)
        assert len(results) <= 2

    async def test_language_filter(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text(SAMPLE_PYTHON_IDENTS)
        (tmp_path / "other.go").write_text(SAMPLE_GO)
        py_results = await search_identifiers(tmp_path, "offset", language="python")
        go_results = await search_identifiers(tmp_path, "offset", language="go")
        # Python results should only be from .py files
        for r in py_results:
            assert r.file_path.endswith(".py")
        for r in go_results:
            assert r.file_path.endswith(".go")

    async def test_context_line_included(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text(SAMPLE_PYTHON_IDENTS)
        results = await search_identifiers(tmp_path, "ApiService", language="python")
        assert len(results) > 0
        # Context should contain actual source code
        assert any("ApiService" in r.context for r in results)

    async def test_no_matches(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text(SAMPLE_PYTHON_IDENTS)
        results = await search_identifiers(tmp_path, "nonexistent_xyz")
        assert results == []
