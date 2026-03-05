"""Repository map: symbol graph construction, PageRank scoring, and concise map generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from codebrain.search.parser import (
    EXTENSION_TO_LANGUAGE,
    TreeSitterParser,
    get_default_parser,
)
from codebrain.search.symbol import SYMBOL_NODE_TYPES, _extract_symbol_name


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class SymbolNode:
    """A symbol in the repository graph."""

    name: str
    kind: str
    file_path: str
    line: int
    signature: str


@dataclass
class SymbolGraph:
    """Directed graph of symbol references."""

    nodes: dict[str, SymbolNode] = field(default_factory=dict)
    # edges[A] = {B, C} means symbol A references symbols B and C
    edges: dict[str, set[str]] = field(default_factory=dict)
    # reverse_edges[B] = {A} means B is referenced by A
    reverse_edges: dict[str, set[str]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Graph construction (tree-sitter identifier matching)
# ---------------------------------------------------------------------------
def _collect_workspace_files(workspace_root: Path) -> list[tuple[Path, str]]:
    """Collect all source files with their language."""
    result: list[tuple[Path, str]] = []
    for ext, lang in EXTENSION_TO_LANGUAGE.items():
        for fp in workspace_root.rglob(f"*{ext}"):
            result.append((fp, lang))
    return sorted(result, key=lambda t: t[0])


def _extract_definitions(
    file_path: Path, language: str, source: bytes, parser: TreeSitterParser
) -> list[SymbolNode]:
    """Extract all symbol definitions from a file."""
    node_types = SYMBOL_NODE_TYPES.get(language, {})
    if not node_types:
        return []

    tree = parser.parse(source, language)
    symbols: list[SymbolNode] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        node_type = getattr(node, "type", "")
        symbol_kind = node_types.get(node_type)
        if symbol_kind is not None:
            name = _extract_symbol_name(node, source)
            if name:
                start_byte = getattr(node, "start_byte", 0)
                end_byte = getattr(node, "end_byte", len(source))
                text = source[start_byte:end_byte].decode("utf-8", errors="replace")
                sig = text.split("\n", 1)[0].strip()
                symbols.append(
                    SymbolNode(
                        name=name,
                        kind=symbol_kind,
                        file_path=str(file_path),
                        line=getattr(node, "start_point", (0,))[0],
                        signature=sig,
                    )
                )
        children = getattr(node, "children", [])
        stack.extend(reversed(children))
    return symbols


def _collect_identifiers(source: bytes, parser: TreeSitterParser, language: str) -> set[str]:
    """Collect all identifier names from a file's AST."""
    tree = parser.parse(source, language)
    identifiers: set[str] = set()
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        node_type = getattr(node, "type", "")
        if node_type == "identifier" or node_type == "type_identifier":
            start = getattr(node, "start_byte", 0)
            end = getattr(node, "end_byte", 0)
            name = source[start:end].decode("utf-8", errors="replace")
            if name:
                identifiers.add(name)
        children = getattr(node, "children", [])
        stack.extend(reversed(children))
    return identifiers


async def build_symbol_graph(
    workspace_root: Path,
    parser: TreeSitterParser | None = None,
) -> SymbolGraph:
    """Build a symbol reference graph for the workspace.

    1. Extract all definitions via tree-sitter.
    2. For each file, collect identifiers and match against definitions.
    3. Build directed edges: file-definitions → referenced-definitions.
    """
    ts_parser = parser or get_default_parser()
    files = _collect_workspace_files(workspace_root)

    graph = SymbolGraph()

    # Pass 1: collect all definitions, keyed by name.
    # Multiple definitions can share a name; we use qualified key "file:name" for uniqueness,
    # but also maintain a name → [keys] index for the identifier-matching pass.
    name_index: dict[str, list[str]] = {}  # name → [qualified_keys]
    file_defs: dict[str, list[str]] = {}  # file → [qualified_keys for defs in that file]

    for fp, lang in files:
        source = fp.read_bytes()
        defs = _extract_definitions(fp, lang, source, ts_parser)
        keys: list[str] = []
        for sym in defs:
            key = f"{sym.file_path}:{sym.name}"
            graph.nodes[key] = sym
            graph.edges.setdefault(key, set())
            graph.reverse_edges.setdefault(key, set())
            name_index.setdefault(sym.name, []).append(key)
            keys.append(key)
        file_defs[str(fp)] = keys

    # Pass 2: for each file, collect identifiers and create edges.
    for fp, lang in files:
        source = fp.read_bytes()
        identifiers = _collect_identifiers(source, ts_parser, lang)
        my_keys = set(file_defs.get(str(fp), []))

        for ident in identifiers:
            targets = name_index.get(ident, [])
            for target_key in targets:
                # Skip self-references (definition referencing itself in same file)
                if target_key in my_keys:
                    continue
                # Add edges from each definition in this file to the referenced symbol
                for src_key in my_keys:
                    graph.edges[src_key].add(target_key)
                    graph.reverse_edges[target_key].add(src_key)

    return graph


# ---------------------------------------------------------------------------
# PageRank
# ---------------------------------------------------------------------------
def pagerank(
    graph: SymbolGraph,
    damping: float = 0.85,
    iterations: int = 20,
) -> dict[str, float]:
    """Compute PageRank scores for symbols in the graph."""
    nodes = list(graph.nodes.keys())
    n = len(nodes)
    if n == 0:
        return {}

    scores: dict[str, float] = {k: 1.0 / n for k in nodes}
    out_degree: dict[str, int] = {k: len(graph.edges.get(k, set())) for k in nodes}

    for _ in range(iterations):
        new_scores: dict[str, float] = {}
        for node in nodes:
            rank_sum = 0.0
            for src in graph.reverse_edges.get(node, set()):
                deg = out_degree.get(src, 0)
                if deg > 0:
                    rank_sum += scores[src] / deg
            new_scores[node] = (1 - damping) / n + damping * rank_sum
        scores = new_scores

    return scores


# ---------------------------------------------------------------------------
# Repomap generation
# ---------------------------------------------------------------------------
@dataclass
class RepomapEntry:
    """A ranked symbol in the repomap."""

    symbol: SymbolNode
    score: float


async def generate_repomap(
    workspace_root: Path,
    max_chars: int = 4096,
    parser: TreeSitterParser | None = None,
) -> str:
    """Generate a concise repository map ranked by symbol importance.

    Returns markdown text fitting within a character budget.
    """
    graph = await build_symbol_graph(workspace_root, parser)
    scores = pagerank(graph)

    # Sort by score descending
    ranked: list[RepomapEntry] = []
    for key, score in sorted(scores.items(), key=lambda x: -x[1]):
        node = graph.nodes[key]
        ranked.append(RepomapEntry(symbol=node, score=score))

    # Group by file, maintaining rank order
    by_file: dict[str, list[RepomapEntry]] = {}
    for entry in ranked:
        by_file.setdefault(entry.symbol.file_path, []).append(entry)

    # Sort files by their top symbol's rank
    file_order = sorted(by_file.keys(), key=lambda f: -by_file[f][0].score)

    # Build markdown within budget
    lines: list[str] = ["# Repository Map", ""]
    char_count = len(lines[0]) + 1

    for fp in file_order:
        # Make path relative to workspace
        try:
            rel = str(Path(fp).relative_to(workspace_root))
        except ValueError:
            rel = fp

        file_header = f"## {rel}"
        if char_count + len(file_header) + 1 > max_chars:
            break

        lines.append(file_header)
        char_count += len(file_header) + 1

        for entry in by_file[fp]:
            sym = entry.symbol
            line = f"- {sym.kind} **{sym.name}** — `{sym.signature}`"
            if char_count + len(line) + 1 > max_chars:
                break
            lines.append(line)
            char_count += len(line) + 1

        lines.append("")
        char_count += 1

    return "\n".join(lines)
