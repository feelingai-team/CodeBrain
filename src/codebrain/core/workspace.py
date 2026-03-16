"""Dynamic workspace management and automatic project root discovery."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from codebrain.core.models import WorkspaceInfo
from codebrain.core.registry import SubProjectRegistry
from codebrain.lsp.factory import build_multi_reporter
from codebrain.lsp.servers.multi import MultiLanguageReporter
from codebrain.search.index import FileWatcher, SymbolIndex

logger = logging.getLogger(__name__)

# Standard markers to identify project roots
ROOT_MARKERS: set[str] = {
    ".git",
    ".hg",
    ".svn",
    "pyproject.toml",
    "package.json",
    "CMakeLists.txt",
    "Cargo.toml",
    "go.mod",
    "requirements.txt",
    "setup.py",
    "tsconfig.json",
    ".clang-format",
    "compile_commands.json",
}


@dataclass
class Workspace:
    """Active workspace instance holding its reporters and index."""

    info: WorkspaceInfo
    reporter: MultiLanguageReporter
    index: SymbolIndex
    watcher: FileWatcher | None = None
    _is_running: bool = False

    async def start(self) -> None:
        """Start all services for this workspace."""
        if self._is_running:
            return
        await self.reporter.start()
        await self.index.build()
        # Start file watcher for incremental index updates (requires watchfiles)
        watcher = FileWatcher(self.index, Path(self.info.root_path))
        try:
            await watcher.start()
            self.watcher = watcher
        except Exception:
            logger.debug("File watcher unavailable, incremental indexing disabled")
        self._is_running = True

    async def stop(self) -> None:
        """Stop all services for this workspace."""
        if not self._is_running:
            return
        if self.watcher is not None:
            await self.watcher.stop()
            self.watcher = None
        await self.reporter.stop()
        self._is_running = False


class WorkspaceManager:
    """Manages multiple dynamic workspaces and routes files to the correct one."""

    def __init__(self, initial_root: Path | None = None) -> None:
        self._workspaces: dict[Path, Workspace] = {}
        self._default_languages: list[str] | None = None
        self.registry: SubProjectRegistry = SubProjectRegistry()

        if initial_root:
            self.add_workspace(initial_root)

    @property
    def workspaces(self) -> list[Workspace]:
        return list(self._workspaces.values())

    def set_default_languages(self, languages: list[str] | None) -> None:
        self._default_languages = languages

    def add_workspace(
        self,
        root: Path,
        name: str | None = None,
        languages: list[str] | None = None,
    ) -> Workspace:
        """Manually add a workspace for the given root."""
        root = root.resolve()
        if root in self._workspaces:
            return self._workspaces[root]

        logger.info("Adding workspace: %s", root)
        info = WorkspaceInfo(
            root_path=str(root),
            name=name or root.name,
            languages=languages or self._default_languages,
        )
        reporter = build_multi_reporter(root, info.languages)
        index = SymbolIndex(root)
        
        ws = Workspace(info=info, reporter=reporter, index=index)
        self._workspaces[root] = ws
        return ws

    async def get_workspace_for_file(
        self, file_path: Path, auto_discover: bool = True
    ) -> Workspace | None:
        """Resolve which workspace a file belongs to (registry-first, then longest prefix match)."""
        file_path = file_path.resolve()

        # Check registry for sub-project awareness
        sub_project = self.registry.resolve(file_path)
        if sub_project:
            for root, ws in self._workspaces.items():
                if sub_project.root.is_relative_to(root):
                    if not ws._is_running:
                        await ws.start()
                    return ws

        # Fall back to existing longest-prefix match
        best_root: Path | None = None
        for root in self._workspaces:
            if file_path.is_relative_to(root):
                if best_root is None or len(str(root)) > len(str(best_root)):
                    best_root = root

        if best_root:
            ws = self._workspaces[best_root]
            if not ws._is_running:
                await ws.start()
            return ws

        # Try auto-discovery
        if auto_discover:
            discovered_root = discover_project_root(file_path)
            if discovered_root:
                ws = self.add_workspace(discovered_root)
                # Scan for sub-projects on auto-discovery
                await self.registry.scan(discovered_root)
                await ws.start()
                return ws

        return None

    async def stop_all(self) -> None:
        """Stop all workspaces."""
        await asyncio.gather(*(ws.stop() for ws in self._workspaces.values()))


def discover_project_root(path: Path) -> Path | None:
    """Walk up from path to find a directory containing any ROOT_MARKERS."""
    current = path.resolve()
    if not current.is_dir():
        current = current.parent

    # Limit search to avoid going to system root /
    for _ in range(20):
        if any((current / marker).exists() for marker in ROOT_MARKERS):
            return current
        if current.parent == current:  # Root reached
            break
        current = current.parent
    
    return None
