"""Hierarchical document symbol extraction using tree-sitter."""

from __future__ import annotations

from pathlib import Path

from codebrain.core.models import DocumentSymbol, Position, Range, SymbolKind
from codebrain.search.parser import TreeSitterParser, get_default_parser, language_for_extension

# Maps (language, node_type) to SymbolKind
_KIND_MAP: dict[str, dict[str, SymbolKind]] = {
    "python": {
        "function_definition": SymbolKind.FUNCTION,
        "class_definition": SymbolKind.CLASS,
        "decorated_definition": SymbolKind.FUNCTION,  # resolved below
    },
    "javascript": {
        "function_declaration": SymbolKind.FUNCTION,
        "class_declaration": SymbolKind.CLASS,
        "method_definition": SymbolKind.METHOD,
        "variable_declarator": SymbolKind.VARIABLE,
    },
    "typescript": {
        "function_declaration": SymbolKind.FUNCTION,
        "class_declaration": SymbolKind.CLASS,
        "interface_declaration": SymbolKind.INTERFACE,
        "type_alias_declaration": SymbolKind.VARIABLE,
        "enum_declaration": SymbolKind.ENUM,
        "method_definition": SymbolKind.METHOD,
        "variable_declarator": SymbolKind.VARIABLE,
    },
    "c": {
        "function_definition": SymbolKind.FUNCTION,
        "struct_specifier": SymbolKind.STRUCT,
        "enum_specifier": SymbolKind.ENUM,
        "type_definition": SymbolKind.VARIABLE,
    },
    "cpp": {
        "function_definition": SymbolKind.FUNCTION,
        "class_specifier": SymbolKind.CLASS,
        "struct_specifier": SymbolKind.STRUCT,
        "enum_specifier": SymbolKind.ENUM,
        "namespace_definition": SymbolKind.NAMESPACE,
        "type_definition": SymbolKind.VARIABLE,
    },
}

# Node types whose children should be recursed into for nested symbols
_CONTAINER_TYPES: dict[str, set[str]] = {
    "python": {"class_definition", "module", "block"},
    "javascript": {"class_declaration", "class_body"},
    "typescript": {"class_declaration", "class_body", "interface_declaration"},
    "c": {"struct_specifier"},
    "cpp": {"class_specifier", "struct_specifier", "namespace_definition"},
}


def _node_range(node: object) -> Range:
    """Convert tree-sitter node positions to a Range."""
    sp = getattr(node, "start_point", None)
    ep = getattr(node, "end_point", None)
    start_row = getattr(sp, "row", 0) if sp is not None else 0
    start_col = getattr(sp, "column", 0) if sp is not None else 0
    end_row = getattr(ep, "row", 0) if ep is not None else 0
    end_col = getattr(ep, "column", 0) if ep is not None else 0
    return Range(
        start=Position(line=start_row, character=start_col),
        end=Position(line=end_row, character=end_col),
    )


def _name_range(node: object) -> Range:
    """Get the range of the name child, or fall back to start of the node."""
    name_node = getattr(node, "child_by_field_name", lambda _: None)("name")
    if name_node is not None:
        return _node_range(name_node)
    return _node_range(node)


def _node_name(node: object, source: bytes) -> str | None:
    """Extract the name text from a node."""
    name_node = getattr(node, "child_by_field_name", lambda _: None)("name")
    if name_node is not None:
        start = getattr(name_node, "start_byte", 0)
        end = getattr(name_node, "end_byte", 0)
        return source[start:end].decode("utf-8", errors="replace")
    return None


def _node_detail(node: object, source: bytes) -> str | None:
    """Extract a short detail string (e.g. return type annotation)."""
    ret = getattr(node, "child_by_field_name", lambda _: None)("return_type")
    if ret is not None:
        start = getattr(ret, "start_byte", 0)
        end = getattr(ret, "end_byte", 0)
        return source[start:end].decode("utf-8", errors="replace")
    return None


def _extract_symbols(
    node: object,
    source: bytes,
    language: str,
) -> list[DocumentSymbol]:
    """Recursively extract DocumentSymbols from a tree-sitter node."""
    kind_map = _KIND_MAP.get(language, {})
    container_types = _CONTAINER_TYPES.get(language, set())

    symbols: list[DocumentSymbol] = []
    children = getattr(node, "children", [])

    for child in children:
        node_type = getattr(child, "type", "")
        symbol_kind = kind_map.get(node_type)

        if symbol_kind is not None:
            name = _node_name(child, source)
            if name is None:
                continue

            # Recurse into container nodes for nested symbols
            nested: list[DocumentSymbol] = []
            if node_type in container_types:
                nested = _extract_symbols(child, source, language)

            symbols.append(
                DocumentSymbol(
                    name=name,
                    kind=symbol_kind,
                    range=_node_range(child),
                    selection_range=_name_range(child),
                    detail=_node_detail(child, source),
                    children=nested,
                )
            )
        elif node_type in container_types:
            # Recurse into containers that aren't themselves symbols (e.g. module)
            symbols.extend(_extract_symbols(child, source, language))

    return symbols


async def get_document_symbols(
    file_path: Path,
    parser: TreeSitterParser | None = None,
) -> list[DocumentSymbol]:
    """Extract hierarchical symbol outline from a file using tree-sitter."""
    ext = file_path.suffix
    language = language_for_extension(ext)
    if language is None:
        return []

    ts_parser = parser or get_default_parser()
    source = file_path.read_bytes()
    tree = ts_parser.parse(source, language)
    return _extract_symbols(tree.root_node, source, language)
