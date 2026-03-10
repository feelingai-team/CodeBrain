"""Symbol search across workspace files using tree-sitter."""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

from codebrain.search.parser import (
    TreeSitterParser,
    collect_source_files,
    get_default_parser,
)

# Node types that represent symbol definitions, per language.
SYMBOL_NODE_TYPES: dict[str, dict[str, str]] = {
    "python": {
        "function_definition": "function",
        "class_definition": "class",
    },
    "javascript": {
        "function_declaration": "function",
        "class_declaration": "class",
        "variable_declarator": "variable",
        "method_definition": "method",
    },
    "typescript": {
        "function_declaration": "function",
        "class_declaration": "class",
        "interface_declaration": "interface",
        "type_alias_declaration": "type",
        "enum_declaration": "enum",
        "variable_declarator": "variable",
        "method_definition": "method",
    },
    "c": {
        "function_definition": "function",
        "struct_specifier": "struct",
        "enum_specifier": "enum",
        "type_definition": "type",
    },
    "cpp": {
        "function_definition": "function",
        "class_specifier": "class",
        "struct_specifier": "struct",
        "enum_specifier": "enum",
        "type_definition": "type",
        "namespace_definition": "namespace",
    },
    "go": {
        "function_declaration": "function",
        "method_declaration": "method",
        "type_spec": "type",  # structs, interfaces, type aliases
        "var_spec": "variable",
        "const_spec": "variable",
    },
}


@dataclass
class SymbolInfo:
    """A symbol found in the workspace."""

    name: str
    kind: str  # function, class, method, variable, etc.
    file_path: str
    line: int
    signature: str | None = None


def _extract_symbol_name(node: object, source: bytes) -> str | None:
    """Extract the name from a definition node."""
    # Most definition nodes have a 'name' child
    name_node = getattr(node, "child_by_field_name", lambda _: None)("name")
    if name_node is not None:
        start = getattr(name_node, "start_byte", 0)
        end = getattr(name_node, "end_byte", 0)
        return source[start:end].decode("utf-8", errors="replace")
    return None


def _extract_signature(node: object, source: bytes) -> str:
    """Extract a one-line signature from the node text."""
    start = getattr(node, "start_byte", 0)
    end = getattr(node, "end_byte", len(source))
    text = source[start:end].decode("utf-8", errors="replace")
    # Return just the first line (the signature line)
    first_line = text.split("\n", 1)[0].strip()
    return first_line


def _match_single(name_lower: str, term: str) -> tuple[bool, int]:
    """Match a single search term against a lowered symbol name.

    Returns (matched, score). Handles exact, substring, glob, and multi-keyword.
    """
    term = term.strip()
    if not term:
        return (False, 0)

    # Glob patterns
    if any(c in term for c in "*?["):
        return (fnmatch(name_lower, term), 80)

    # Exact match
    if name_lower == term:
        return (True, 100)

    # Substring match
    if term in name_lower:
        return (True, 80)

    # Multi-keyword: split on whitespace/underscores/hyphens, all must match
    keywords = term.replace("_", " ").replace("-", " ").split()
    if len(keywords) > 1:
        if all(kw in name_lower for kw in keywords):
            return (True, 60)

    return (False, 0)


def _matches_query(name: str, query: str) -> tuple[bool, int]:
    """Check if a symbol name matches the search query.

    Returns (matched, score) where higher score = better match.

    Supports:
    - Exact/substring match: "StreamParser"
    - Glob patterns: "Stream*"
    - Multi-keyword (AND): "stream parser" — all keywords must appear
    - Pipe-separated (OR): "StreamParser|FrameParser" — best match wins
    """
    name_lower = name.lower()
    query_lower = query.lower()

    # Pipe-separated OR: evaluate each alternative, return best match
    if "|" in query_lower:
        best_score = 0
        for alt in query_lower.split("|"):
            matched, score = _match_single(name_lower, alt)
            if matched and score > best_score:
                best_score = score
        return (best_score > 0, best_score)

    return _match_single(name_lower, query_lower)


def _collect_language_files(
    workspace_root: Path, language: str | None
) -> list[tuple[Path, str]]:
    """Collect files with their language, optionally filtered by language."""
    return collect_source_files(workspace_root, language)


async def search_symbol(
    workspace_root: Path,
    query: str,
    kind: str | None = None,
    language: str | None = None,
    max_results: int = 100,
    parser: TreeSitterParser | None = None,
) -> list[SymbolInfo]:
    """Search for symbols by name across workspace files.

    Args:
        workspace_root: Root directory to search.
        query: Symbol name or glob pattern to match.
        kind: Optional filter by kind (e.g. "function", "class").
        language: Optional filter by language.
        max_results: Maximum number of results to return.
        parser: Optional parser instance; uses default singleton if None.
    """
    ts_parser = parser or get_default_parser()
    files = _collect_language_files(workspace_root, language)

    scored: list[tuple[int, SymbolInfo]] = []
    for file_path, lang in files:
        node_types = SYMBOL_NODE_TYPES.get(lang, {})
        if not node_types:
            continue

        source = file_path.read_bytes()
        tree = ts_parser.parse(source, lang)

        # Walk the tree looking for symbol definition nodes
        stack = [tree.root_node]
        while stack:
            node = stack.pop()
            node_type = getattr(node, "type", "")
            symbol_kind = node_types.get(node_type)

            if symbol_kind is not None:
                name = _extract_symbol_name(node, source)
                if name:
                    matched, score = _matches_query(name, query)
                    if matched and (kind is None or kind == symbol_kind):
                        sig = _extract_signature(node, source)
                        scored.append((
                            score,
                            SymbolInfo(
                                name=name,
                                kind=symbol_kind,
                                file_path=str(file_path),
                                line=getattr(node, "start_point", (0,))[0],
                                signature=sig,
                            ),
                        ))

            # Add children in reverse so we process left-to-right
            children = getattr(node, "children", [])
            stack.extend(reversed(children))

    # Sort by score descending, then truncate
    scored.sort(key=lambda x: x[0], reverse=True)
    return [sym for _, sym in scored[:max_results]]


# ---------------------------------------------------------------------------
# Identifier search — matches ALL identifier usages in the AST
# ---------------------------------------------------------------------------

@dataclass
class IdentifierMatch:
    """An identifier usage found in the workspace (not just definitions)."""

    name: str
    file_path: str
    line: int  # 0-indexed
    context: str  # The source line containing the identifier


async def search_identifiers(
    workspace_root: Path,
    query: str,
    language: str | None = None,
    max_results: int = 100,
    parser: TreeSitterParser | None = None,
) -> list[IdentifierMatch]:
    """Search for identifier usages (method calls, variable refs, field access) by name.

    Unlike search_symbol which only finds definitions, this searches ALL identifiers
    in the AST including method selectors (db.Offset), field access (obj.prop), etc.
    """
    from codebrain.search.repomap import IDENTIFIER_NODE_TYPES

    ts_parser = parser or get_default_parser()
    files = _collect_language_files(workspace_root, language)

    scored: list[tuple[int, IdentifierMatch]] = []
    for file_path, lang in files:
        source = file_path.read_bytes()
        tree = ts_parser.parse(source, lang)
        lines = source.decode("utf-8", errors="replace").splitlines()

        # Track seen (file, line) to deduplicate multiple matches on the same line
        seen_lines: set[int] = set()

        stack = [tree.root_node]
        while stack:
            node = stack.pop()
            node_type = getattr(node, "type", "")

            if node_type in IDENTIFIER_NODE_TYPES:
                start = getattr(node, "start_byte", 0)
                end = getattr(node, "end_byte", 0)
                name = source[start:end].decode("utf-8", errors="replace")
                if name:
                    matched, score = _matches_query(name, query)
                    if matched:
                        line_num = getattr(node, "start_point", (0,))[0]
                        if line_num not in seen_lines:
                            seen_lines.add(line_num)
                            ctx = lines[line_num].strip() if line_num < len(lines) else ""
                            if len(ctx) > 200:
                                ctx = ctx[:197] + "..."
                            scored.append((
                                score,
                                IdentifierMatch(
                                    name=name,
                                    file_path=str(file_path),
                                    line=line_num,
                                    context=ctx,
                                ),
                            ))

            children = getattr(node, "children", [])
            stack.extend(reversed(children))

        if len(scored) >= max_results:
            break

    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored[:max_results]]
