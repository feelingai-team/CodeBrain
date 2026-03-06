"""Incremental symbol index with file-watching support.

The SymbolIndex maintains an in-memory symbol graph that can be updated
incrementally when files change, avoiding full workspace re-scans.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from codebrain.search.parser import (
    TreeSitterParser,
    collect_source_files,
    get_default_parser,
    language_for_extension,
)
from codebrain.search.repomap import (
    RepomapEntry,
    SymbolGraph,
    SymbolNode,
    _collect_identifiers,
    _extract_definitions,
    pagerank,
)

logger = logging.getLogger(__name__)


class SymbolIndex:
    """Incremental, in-memory symbol index for a workspace.

    Maintains a SymbolGraph that can be updated file-by-file in ~50-200ms
    instead of requiring a full workspace re-scan.
    """

    def __init__(
        self,
        workspace_root: Path,
        parser: TreeSitterParser | None = None,
    ) -> None:
        self._workspace_root = workspace_root
        self._parser = parser or get_default_parser()
        self._graph = SymbolGraph()

        # Per-file tracking for incremental updates
        self._file_keys: dict[str, list[str]] = {}  # file → [qualified keys]
        self._file_identifiers: dict[str, set[str]] = {}  # file → {identifier names}
        self._name_index: dict[str, list[str]] = {}  # symbol name → [qualified keys]

        self._built = False
        self._rank_cache: dict[str, float] | None = None

    @property
    def is_built(self) -> bool:
        return self._built

    @property
    def graph(self) -> SymbolGraph:
        return self._graph

    # ------------------------------------------------------------------
    # Full build
    # ------------------------------------------------------------------
    async def build(self) -> None:
        """Perform a full workspace scan and build the index."""
        self._graph = SymbolGraph()
        self._file_keys.clear()
        self._file_identifiers.clear()
        self._name_index.clear()
        self._rank_cache = None

        files = self._collect_files()

        # Pass 1: extract definitions
        for fp, lang in files:
            source = fp.read_bytes()
            self._index_file_definitions(fp, lang, source)

        # Pass 2: extract identifiers and build edges
        for fp, lang in files:
            source = fp.read_bytes()
            self._index_file_edges(fp, lang, source)

        self._built = True
        logger.info(
            "Index built: %d symbols, %d files",
            len(self._graph.nodes),
            len(self._file_keys),
        )

    # ------------------------------------------------------------------
    # Incremental update
    # ------------------------------------------------------------------
    async def update(self, changed_files: list[Path]) -> None:
        """Incrementally update the index for changed files.

        For each changed file:
        1. Remove its old definitions and edges.
        2. Re-parse and re-index.
        3. Recompute edges for files that referenced symbols in the changed file.
        """
        if not self._built:
            await self.build()
            return

        self._rank_cache = None
        affected_names: set[str] = set()

        for fp in changed_files:
            fp = fp.resolve()
            fp_str = str(fp)
            lang = language_for_extension(fp.suffix)
            if lang is None:
                continue

            # Collect names of symbols that were in this file (for edge recomputation)
            for key in self._file_keys.get(fp_str, []):
                node = self._graph.nodes.get(key)
                if node:
                    affected_names.add(node.name)

            # Remove old data for this file
            self._remove_file(fp_str)

            # Re-index if file still exists
            if fp.exists():
                source = fp.read_bytes()
                self._index_file_definitions(fp, lang, source)
                # Collect new symbol names too
                for key in self._file_keys.get(fp_str, []):
                    node = self._graph.nodes.get(key)
                    if node:
                        affected_names.add(node.name)
                self._index_file_edges(fp, lang, source)

        # Recompute edges for other files that reference affected symbol names
        if affected_names:
            self._recompute_edges_for_affected(affected_names, changed_files)

    async def remove(self, deleted_files: list[Path]) -> None:
        """Remove deleted files from the index."""
        self._rank_cache = None
        affected_names: set[str] = set()
        for fp in deleted_files:
            fp_str = str(fp.resolve())
            for key in self._file_keys.get(fp_str, []):
                node = self._graph.nodes.get(key)
                if node:
                    affected_names.add(node.name)
            self._remove_file(fp_str)

        if affected_names:
            self._recompute_edges_for_affected(affected_names, deleted_files)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------
    def query(
        self,
        name: str | None = None,
        kind: str | None = None,
        file_path: Path | None = None,
    ) -> list[SymbolNode]:
        """Query symbols by name, kind, and/or file path."""
        results: list[SymbolNode] = []
        for node in self._graph.nodes.values():
            if name is not None and name.lower() not in node.name.lower():
                continue
            if kind is not None and node.kind != kind:
                continue
            if file_path is not None and node.file_path != str(file_path):
                continue
            results.append(node)
        return results

    def get_ranks(self) -> dict[str, float]:
        """Return PageRank scores, using cache when available."""
        if self._rank_cache is None:
            self._rank_cache = pagerank(self._graph)
        assert self._rank_cache is not None
        return self._rank_cache

    def generate_repomap(self, max_chars: int = 4096) -> str:
        """Generate a repomap from the cached index (no re-scan needed)."""
        scores = self.get_ranks()

        ranked: list[RepomapEntry] = []
        for key, score in sorted(scores.items(), key=lambda x: -x[1]):
            node = self._graph.nodes.get(key)
            if node:
                ranked.append(RepomapEntry(symbol=node, score=score))

        by_file: dict[str, list[RepomapEntry]] = {}
        for entry in ranked:
            by_file.setdefault(entry.symbol.file_path, []).append(entry)

        file_order = sorted(by_file.keys(), key=lambda f: -by_file[f][0].score)

        lines: list[str] = ["# Repository Map", ""]
        char_count = len(lines[0]) + 1

        for fp in file_order:
            try:
                rel = str(Path(fp).relative_to(self._workspace_root))
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

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _collect_files(self) -> list[tuple[Path, str]]:
        return collect_source_files(self._workspace_root)

    def _index_file_definitions(
        self, file_path: Path, language: str, source: bytes
    ) -> None:
        """Extract definitions from a file and add them to the graph."""
        defs = _extract_definitions(file_path, language, source, self._parser)
        keys: list[str] = []
        for sym in defs:
            key = f"{sym.file_path}:{sym.name}"
            self._graph.nodes[key] = sym
            self._graph.edges.setdefault(key, set())
            self._graph.reverse_edges.setdefault(key, set())
            self._name_index.setdefault(sym.name, []).append(key)
            keys.append(key)
        self._file_keys[str(file_path)] = keys

    def _index_file_edges(
        self, file_path: Path, language: str, source: bytes
    ) -> None:
        """Collect identifiers from a file and build cross-file edges."""
        identifiers = _collect_identifiers(source, self._parser, language)
        self._file_identifiers[str(file_path)] = identifiers
        my_keys = set(self._file_keys.get(str(file_path), []))

        for ident in identifiers:
            targets = self._name_index.get(ident, [])
            for target_key in targets:
                if target_key in my_keys:
                    continue
                for src_key in my_keys:
                    self._graph.edges[src_key].add(target_key)
                    self._graph.reverse_edges[target_key].add(src_key)

    def _remove_file(self, fp_str: str) -> None:
        """Remove all data for a file from the index."""
        old_keys = self._file_keys.pop(fp_str, [])
        self._file_identifiers.pop(fp_str, None)

        for key in old_keys:
            node = self._graph.nodes.pop(key, None)
            if node:
                # Remove from name index
                name_entries = self._name_index.get(node.name, [])
                if key in name_entries:
                    name_entries.remove(key)
                    if not name_entries:
                        del self._name_index[node.name]

            # Remove all outgoing edges
            targets = self._graph.edges.pop(key, set())
            for target in targets:
                rev = self._graph.reverse_edges.get(target)
                if rev:
                    rev.discard(key)

            # Remove all incoming edges
            sources = self._graph.reverse_edges.pop(key, set())
            for src in sources:
                fwd = self._graph.edges.get(src)
                if fwd:
                    fwd.discard(key)

    def _recompute_edges_for_affected(
        self, affected_names: set[str], skip_files: list[Path]
    ) -> None:
        """Recompute edges for files that reference any of the affected symbol names."""
        skip_strs = {str(fp.resolve()) for fp in skip_files}

        for fp_str, identifiers in self._file_identifiers.items():
            if fp_str in skip_strs:
                continue
            # Check if this file uses any affected names
            if not affected_names.intersection(identifiers):
                continue

            # Remove old edges from this file's symbols, then rebuild
            my_keys = self._file_keys.get(fp_str, [])
            for src_key in my_keys:
                old_targets = self._graph.edges.get(src_key, set()).copy()
                for target in old_targets:
                    self._graph.edges[src_key].discard(target)
                    rev = self._graph.reverse_edges.get(target)
                    if rev:
                        rev.discard(src_key)

            # Rebuild edges
            my_key_set = set(my_keys)
            for ident in identifiers:
                targets = self._name_index.get(ident, [])
                for target_key in targets:
                    if target_key in my_key_set:
                        continue
                    for src_key in my_keys:
                        self._graph.edges[src_key].add(target_key)
                        self._graph.reverse_edges[target_key].add(src_key)


# ---------------------------------------------------------------------------
# File watcher (requires optional 'watchfiles' dependency)
# ---------------------------------------------------------------------------
class FileWatcher:
    """Watches workspace for file changes and triggers incremental index updates.

    Requires the `watchfiles` optional dependency: pip install codebrain[watch]
    """

    def __init__(self, index: SymbolIndex, workspace_root: Path) -> None:
        self._index = index
        self._workspace_root = workspace_root
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        """Start watching for file changes in the background."""
        if self.is_running:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._watch_loop())
        logger.info("File watcher started for %s", self._workspace_root)

    async def stop(self) -> None:
        """Stop the file watcher."""
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("File watcher stopped")

    async def _watch_loop(self) -> None:
        """Main watch loop using watchfiles."""
        try:
            from watchfiles import Change, awatch
        except ImportError:
            logger.error("watchfiles not installed. Install with: pip install codebrain[watch]")
            return

        # Filter to only watch source files we care about
        from codebrain.search.parser import EXTENSION_TO_LANGUAGE

        extensions = set(EXTENSION_TO_LANGUAGE.keys())

        def _filter(_change: Change, path: str) -> bool:
            return Path(path).suffix in extensions

        try:
            async for changes in awatch(
                self._workspace_root,
                watch_filter=_filter,
                stop_event=self._stop_event,
            ):
                changed: list[Path] = []
                deleted: list[Path] = []
                for change_type, path_str in changes:
                    p = Path(path_str)
                    if change_type == Change.deleted:
                        deleted.append(p)
                    else:
                        changed.append(p)

                if deleted:
                    await self._index.remove(deleted)
                    logger.debug("Removed %d deleted files from index", len(deleted))
                if changed:
                    await self._index.update(changed)
                    logger.debug("Updated %d changed files in index", len(changed))
        except asyncio.CancelledError:
            return
