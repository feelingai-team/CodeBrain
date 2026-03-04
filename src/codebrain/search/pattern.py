"""Tree-sitter based structural pattern search."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from codebrain.search.parser import (
    EXTENSION_TO_LANGUAGE,
    TreeSitterParser,
    get_default_parser,
)


@dataclass
class PatternMatch:
    """A single match from a structural pattern search."""

    file_path: str
    start_line: int
    end_line: int
    text: str
    captures: dict[str, str] = field(default_factory=dict)


def _get_node_text(node: object, source: bytes) -> str:
    """Extract text for a tree-sitter node from source bytes."""
    # node has start_byte and end_byte attributes
    start = getattr(node, "start_byte", 0)
    end = getattr(node, "end_byte", len(source))
    return source[start:end].decode("utf-8", errors="replace")


def _collect_files(
    workspace_root: Path,
    language: str,
    file_paths: list[Path] | None = None,
) -> list[Path]:
    """Collect files matching the target language."""
    if file_paths is not None:
        return [p for p in file_paths if p.is_file()]

    exts = {ext for ext, lang in EXTENSION_TO_LANGUAGE.items() if lang == language}
    result: list[Path] = []
    for ext in exts:
        result.extend(workspace_root.rglob(f"*{ext}"))
    return sorted(result)


async def search_pattern(
    workspace_root: Path,
    pattern: str,
    language: str,
    file_paths: list[Path] | None = None,
    max_results: int = 100,
    parser: TreeSitterParser | None = None,
) -> list[PatternMatch]:
    """Search for structural code patterns using tree-sitter queries.

    Args:
        workspace_root: Root directory to search.
        pattern: Tree-sitter S-expression query pattern.
        language: Target language (e.g. "python", "typescript").
        file_paths: Specific files to search, or None for all matching files.
        max_results: Maximum number of results to return.
        parser: Optional parser instance; uses default singleton if None.
    """
    from tree_sitter import Query, QueryCursor

    ts_parser = parser or get_default_parser()
    lang = ts_parser.get_language(language)
    query = Query(lang, pattern)
    files = _collect_files(workspace_root, language, file_paths)

    matches: list[PatternMatch] = []
    for file_path in files:
        if len(matches) >= max_results:
            break

        source = file_path.read_bytes()
        tree = ts_parser.parse(source, language)

        cursor = QueryCursor(query)
        captures = cursor.captures(tree.root_node)

        # captures is dict[str, list[Node]]
        # Flatten all captured nodes into PatternMatch objects
        seen_ranges: set[tuple[int, int]] = set()
        for capture_name, nodes in captures.items():
            for node in nodes:
                key = (node.start_point.row, node.end_point.row)
                if key in seen_ranges:
                    continue
                seen_ranges.add(key)

                text = _get_node_text(node, source)
                match = PatternMatch(
                    file_path=str(file_path),
                    start_line=node.start_point.row,
                    end_line=node.end_point.row,
                    text=text,
                    captures={capture_name: text},
                )
                matches.append(match)

                if len(matches) >= max_results:
                    break
            if len(matches) >= max_results:
                break

    return matches
