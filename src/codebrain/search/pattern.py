"""Tree-sitter based structural pattern search."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class PatternMatch:
    """A single match from a structural pattern search."""

    file_path: str
    start_line: int
    end_line: int
    text: str
    captures: dict[str, str]


async def search_pattern(
    workspace_root: Path,
    pattern: str,
    language: str,
    file_paths: list[Path] | None = None,
    max_results: int = 100,
) -> list[PatternMatch]:
    """Search for structural code patterns using tree-sitter queries."""
    raise NotImplementedError
