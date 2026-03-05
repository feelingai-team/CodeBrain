"""Tests for incremental symbol index."""

from __future__ import annotations

from pathlib import Path

import pytest

from codebrain.search.index import SymbolIndex
from codebrain.search.parser import TreeSitterParser

MODULE_A = """\
class Greeter:
    def greet(self, name: str) -> str:
        return "Hello, " + name
"""

MODULE_B = """\
from module_a import Greeter

def format_name(name: str) -> str:
    return name.title()

def helper() -> Greeter:
    return Greeter()
"""

MODULE_C = """\
def standalone() -> int:
    return 42
"""


@pytest.fixture
def ts_parser() -> TreeSitterParser:
    return TreeSitterParser()


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "module_a.py").write_text(MODULE_A)
    (tmp_path / "module_b.py").write_text(MODULE_B)
    return tmp_path


@pytest.fixture
async def built_index(workspace: Path, ts_parser: TreeSitterParser) -> SymbolIndex:
    index = SymbolIndex(workspace, ts_parser)
    await index.build()
    return index


# --- Full build ---


class TestBuild:
    async def test_is_built(self, built_index: SymbolIndex) -> None:
        assert built_index.is_built

    async def test_not_built_initially(
        self, workspace: Path, ts_parser: TreeSitterParser
    ) -> None:
        index = SymbolIndex(workspace, ts_parser)
        assert not index.is_built

    async def test_finds_all_symbols(self, built_index: SymbolIndex) -> None:
        names = {n.name for n in built_index.graph.nodes.values()}
        assert "Greeter" in names
        assert "greet" in names
        assert "format_name" in names
        assert "helper" in names

    async def test_builds_edges(self, built_index: SymbolIndex) -> None:
        greeter_key = next(
            k for k, v in built_index.graph.nodes.items() if v.name == "Greeter"
        )
        assert len(built_index.graph.reverse_edges[greeter_key]) > 0


# --- Incremental update ---


class TestIncrementalUpdate:
    async def test_add_new_file(
        self, workspace: Path, built_index: SymbolIndex
    ) -> None:
        new_file = workspace / "module_c.py"
        new_file.write_text(MODULE_C)

        await built_index.update([new_file])

        names = {n.name for n in built_index.graph.nodes.values()}
        assert "standalone" in names

    async def test_modify_existing_file(
        self, workspace: Path, built_index: SymbolIndex
    ) -> None:
        # Rename Greeter to Welcomer
        modified = MODULE_A.replace("Greeter", "Welcomer")
        (workspace / "module_a.py").write_text(modified)

        await built_index.update([workspace / "module_a.py"])

        names = {n.name for n in built_index.graph.nodes.values()}
        assert "Welcomer" in names
        assert "Greeter" not in names

    async def test_delete_file(
        self, workspace: Path, built_index: SymbolIndex
    ) -> None:
        (workspace / "module_b.py").unlink()

        await built_index.remove([workspace / "module_b.py"])

        names = {n.name for n in built_index.graph.nodes.values()}
        assert "format_name" not in names
        assert "helper" not in names
        # module_a symbols should still be there
        assert "Greeter" in names

    async def test_update_nonexistent_file_is_removal(
        self, workspace: Path, built_index: SymbolIndex
    ) -> None:
        gone = workspace / "module_b.py"
        gone.unlink()

        # update() on a deleted file should act as removal
        await built_index.update([gone])

        names = {n.name for n in built_index.graph.nodes.values()}
        assert "format_name" not in names

    async def test_edges_updated_after_change(
        self, workspace: Path, built_index: SymbolIndex
    ) -> None:
        # module_b references Greeter; after removing Greeter, those edges should vanish
        (workspace / "module_a.py").write_text("def new_func(): pass\n")
        await built_index.update([workspace / "module_a.py"])

        # No node named Greeter should remain in reverse_edges
        for key in built_index.graph.reverse_edges:
            node = built_index.graph.nodes.get(key)
            if node:
                assert node.name != "Greeter"

    async def test_rank_cache_invalidated(
        self, workspace: Path, built_index: SymbolIndex
    ) -> None:
        # Compute ranks, then update
        _ = built_index.get_ranks()
        assert built_index._rank_cache is not None

        (workspace / "module_c.py").write_text(MODULE_C)
        await built_index.update([workspace / "module_c.py"])

        # Cache should be cleared
        assert built_index._rank_cache is None

    async def test_update_on_unbuilt_triggers_full_build(
        self, workspace: Path, ts_parser: TreeSitterParser
    ) -> None:
        index = SymbolIndex(workspace, ts_parser)
        assert not index.is_built

        await index.update([workspace / "module_a.py"])

        assert index.is_built
        names = {n.name for n in index.graph.nodes.values()}
        assert "Greeter" in names


# --- Query ---


class TestQuery:
    async def test_query_by_name(self, built_index: SymbolIndex) -> None:
        results = built_index.query(name="greet")
        assert any(n.name == "greet" for n in results)

    async def test_query_by_kind(self, built_index: SymbolIndex) -> None:
        results = built_index.query(kind="class")
        assert all(n.kind == "class" for n in results)
        assert any(n.name == "Greeter" for n in results)

    async def test_query_by_file(
        self, workspace: Path, built_index: SymbolIndex
    ) -> None:
        results = built_index.query(file_path=workspace / "module_b.py")
        names = {n.name for n in results}
        assert "format_name" in names
        assert "Greeter" not in names  # Greeter is in module_a

    async def test_query_no_match(self, built_index: SymbolIndex) -> None:
        results = built_index.query(name="nonexistent_xyz")
        assert results == []


# --- Repomap from index ---


class TestIndexRepomap:
    async def test_generates_markdown(self, built_index: SymbolIndex) -> None:
        result = built_index.generate_repomap()
        assert result.startswith("# Repository Map")
        assert "Greeter" in result

    async def test_respects_budget(self, built_index: SymbolIndex) -> None:
        result = built_index.generate_repomap(max_chars=100)
        assert len(result) <= 150  # small overshoot tolerance


# --- PageRank ---


class TestIndexRanks:
    async def test_ranks_non_empty(self, built_index: SymbolIndex) -> None:
        ranks = built_index.get_ranks()
        assert len(ranks) > 0

    async def test_ranks_cached(self, built_index: SymbolIndex) -> None:
        r1 = built_index.get_ranks()
        r2 = built_index.get_ranks()
        assert r1 is r2  # same object, cached
