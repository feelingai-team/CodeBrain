"""Tests for repomap: symbol graph, PageRank, and map generation."""

from __future__ import annotations

from pathlib import Path

import pytest

from codebrain.search.parser import TreeSitterParser
from codebrain.search.repomap import (
    SymbolGraph,
    SymbolNode,
    build_symbol_graph,
    generate_repomap,
    pagerank,
)

# Two files: module_a defines `Greeter` and references `format_name` from module_b.
# module_b defines `format_name` and references `Greeter`.
MODULE_A = """\
from module_b import format_name

class Greeter:
    def greet(self, name: str) -> str:
        return format_name(name)
"""

MODULE_B = """\
from module_a import Greeter

def format_name(name: str) -> str:
    return name.title()

def helper() -> Greeter:
    return Greeter()
"""


@pytest.fixture
def multi_file_workspace(tmp_path: Path) -> Path:
    (tmp_path / "module_a.py").write_text(MODULE_A)
    (tmp_path / "module_b.py").write_text(MODULE_B)
    return tmp_path


@pytest.fixture
def ts_parser() -> TreeSitterParser:
    return TreeSitterParser()


# --- Symbol graph construction ---


class TestBuildSymbolGraph:
    async def test_finds_definitions(
        self, multi_file_workspace: Path, ts_parser: TreeSitterParser
    ) -> None:
        graph = await build_symbol_graph(multi_file_workspace, ts_parser)
        names = {n.name for n in graph.nodes.values()}
        assert "Greeter" in names
        assert "greet" in names
        assert "format_name" in names
        assert "helper" in names

    async def test_builds_cross_file_edges(
        self, multi_file_workspace: Path, ts_parser: TreeSitterParser
    ) -> None:
        graph = await build_symbol_graph(multi_file_workspace, ts_parser)
        # module_b references Greeter (defined in module_a)
        greeter_key = next(k for k, v in graph.nodes.items() if v.name == "Greeter")
        assert len(graph.reverse_edges[greeter_key]) > 0

    async def test_no_self_referencing_edges(
        self, multi_file_workspace: Path, ts_parser: TreeSitterParser
    ) -> None:
        graph = await build_symbol_graph(multi_file_workspace, ts_parser)
        for key, targets in graph.edges.items():
            file = graph.nodes[key].file_path
            for t in targets:
                # All edges should be cross-file (we skip same-file self-refs)
                assert graph.nodes[t].file_path != file

    async def test_empty_workspace(self, tmp_path: Path, ts_parser: TreeSitterParser) -> None:
        graph = await build_symbol_graph(tmp_path, ts_parser)
        assert len(graph.nodes) == 0


# --- PageRank ---


class TestPageRank:
    def test_empty_graph(self) -> None:
        graph = SymbolGraph()
        scores = pagerank(graph)
        assert scores == {}

    def test_single_node(self) -> None:
        graph = SymbolGraph()
        graph.nodes["a"] = SymbolNode("a", "function", "f.py", 0, "def a()")
        graph.edges["a"] = set()
        graph.reverse_edges["a"] = set()
        scores = pagerank(graph)
        assert "a" in scores
        assert scores["a"] > 0

    def test_highly_referenced_scores_higher(self) -> None:
        """A node referenced by many others should have a higher rank."""
        graph = SymbolGraph()
        # Create a "hub" node and several leaf nodes that all reference it
        for name in ["hub", "leaf1", "leaf2", "leaf3"]:
            graph.nodes[name] = SymbolNode(name, "function", "f.py", 0, f"def {name}()")
            graph.edges[name] = set()
            graph.reverse_edges[name] = set()

        for leaf in ["leaf1", "leaf2", "leaf3"]:
            graph.edges[leaf].add("hub")
            graph.reverse_edges["hub"].add(leaf)

        scores = pagerank(graph)
        assert scores["hub"] > scores["leaf1"]
        assert scores["hub"] > scores["leaf2"]
        assert scores["hub"] > scores["leaf3"]

    def test_downstream_node_scores_higher(self) -> None:
        """In a chain A→B→C, C (the sink) should score highest."""
        graph = SymbolGraph()
        for name in ["a", "b", "c"]:
            graph.nodes[name] = SymbolNode(name, "function", "f.py", 0, f"def {name}()")
            graph.edges[name] = set()
            graph.reverse_edges[name] = set()
        graph.edges["a"].add("b")
        graph.reverse_edges["b"].add("a")
        graph.edges["b"].add("c")
        graph.reverse_edges["c"].add("b")

        scores = pagerank(graph)
        assert scores["c"] > scores["b"]
        assert scores["b"] > scores["a"]


# --- Repomap generation ---


class TestGenerateRepomap:
    async def test_generates_markdown(
        self, multi_file_workspace: Path, ts_parser: TreeSitterParser
    ) -> None:
        result = await generate_repomap(multi_file_workspace, parser=ts_parser)
        assert result.startswith("# Repository Map")
        assert "Greeter" in result
        assert "format_name" in result

    async def test_respects_char_budget(
        self, multi_file_workspace: Path, ts_parser: TreeSitterParser
    ) -> None:
        result = await generate_repomap(multi_file_workspace, max_chars=200, parser=ts_parser)
        assert len(result) <= 250  # allow small overshoot for final line

    async def test_empty_workspace(self, tmp_path: Path, ts_parser: TreeSitterParser) -> None:
        result = await generate_repomap(tmp_path, parser=ts_parser)
        assert "Repository Map" in result
