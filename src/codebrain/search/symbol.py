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


def _matches_query(name: str, query: str) -> bool:
    """Check if a symbol name matches the search query (case-insensitive glob)."""
    # Support glob patterns
    if any(c in query for c in "*?["):
        return fnmatch(name.lower(), query.lower())
    # Plain substring match
    return query.lower() in name.lower()


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

    symbols: list[SymbolInfo] = []
    for file_path, lang in files:
        if len(symbols) >= max_results:
            break

        node_types = SYMBOL_NODE_TYPES.get(lang, {})
        if not node_types:
            continue

        source = file_path.read_bytes()
        tree = ts_parser.parse(source, lang)

        # Walk the tree looking for symbol definition nodes
        stack = [tree.root_node]
        while stack and len(symbols) < max_results:
            node = stack.pop()
            node_type = getattr(node, "type", "")
            symbol_kind = node_types.get(node_type)

            if symbol_kind is not None:
                name = _extract_symbol_name(node, source)
                if name and _matches_query(name, query):
                    if kind is None or kind == symbol_kind:
                        sig = _extract_signature(node, source)
                        symbols.append(
                            SymbolInfo(
                                name=name,
                                kind=symbol_kind,
                                file_path=str(file_path),
                                line=getattr(node, "start_point", (0,))[0],
                                signature=sig,
                            )
                        )

            # Add children in reverse so we process left-to-right
            children = getattr(node, "children", [])
            stack.extend(reversed(children))

    return symbols
