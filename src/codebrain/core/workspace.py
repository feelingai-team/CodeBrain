"""Dynamic workspace management and automatic project root discovery."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from codebrain.core.models import SubProject, WorkspaceInfo
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
        sub_project: SubProject | None = None,
    ) -> Workspace:
        """Manually add a workspace for the given root.

        If sub_project is provided, its toolchain config is passed to the
        reporter factory so LSP servers get the correct venv/tsconfig/go.mod.
        """
        root = root.resolve()
        if root in self._workspaces:
            return self._workspaces[root]

        logger.info("Adding workspace: %s", root)
        info = WorkspaceInfo(
            root_path=str(root),
            name=name or root.name,
            languages=languages or self._default_languages,
        )
        reporter = build_multi_reporter(root, info.languages, sub_project=sub_project)
        index = SymbolIndex(root)

        ws = Workspace(info=info, reporter=reporter, index=index)
        self._workspaces[root] = ws
        return ws

    async def get_workspace_for_file(
        self, file_path: Path, auto_discover: bool = True
    ) -> Workspace | None:
        """Resolve which workspace a file belongs to.

        Priority:
        1. Exact sub-project workspace (if already created for this sub-project root)
        2. Create a new workspace for the sub-project (lazy, with correct toolchain)
        3. Existing workspace via longest-prefix match
        4. Auto-discover workspace root
        """
        file_path = file_path.resolve()

        # 1. Check registry for sub-project awareness
        sub_project = self.registry.resolve(file_path)
        if sub_project:
            # Do we already have a workspace for this exact sub-project root?
            if sub_project.root in self._workspaces:
                ws = self._workspaces[sub_project.root]
                if not ws._is_running:
                    await ws.start()
                return ws

            # Create a new workspace for this sub-project with its toolchain
            sp_langs = [lang.value for lang in sub_project.languages]
            ws = self.add_workspace(
                sub_project.root,
                languages=sp_langs,
                sub_project=sub_project,
            )
            await ws.start()
            logger.info(
                "Created sub-project workspace: %s [%s]",
                sub_project.root, ", ".join(sp_langs),
            )
            return ws

        # 2. Fall back to existing longest-prefix match
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

        # 3. Try auto-discovery
        if auto_discover:
            discovered_root = discover_project_root(file_path)
            if discovered_root:
                # Scan for sub-projects first, then check if file is in one
                await self.registry.scan(discovered_root)
                sub_project = self.registry.resolve(file_path)
                if sub_project and sub_project.root != discovered_root:
                    # File belongs to a sub-project — create workspace at sub-project root
                    sp_langs = [lang.value for lang in sub_project.languages]
                    ws = self.add_workspace(
                        sub_project.root,
                        languages=sp_langs,
                        sub_project=sub_project,
                    )
                else:
                    ws = self.add_workspace(discovered_root)
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
