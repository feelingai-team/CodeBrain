"""Symbol search across workspace files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class SymbolInfo:
    """A symbol found in the workspace."""

    name: str
    kind: str  # function, class, method, variable, etc.
    file_path: str
    line: int
    signature: str | None = None


async def search_symbol(
    workspace_root: Path,
    query: str,
    kind: str | None = None,
    language: str | None = None,
    max_results: int = 100,
) -> list[SymbolInfo]:
    """Search for symbols by name across workspace files."""
    raise NotImplementedError
