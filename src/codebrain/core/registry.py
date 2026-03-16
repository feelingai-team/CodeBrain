"""Sub-project registry for monorepo-aware toolchain detection."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from codebrain.core.models import Language, SubProject
from codebrain.core.toolchain import detect_toolchain, load_codebrain_overrides

logger = logging.getLogger(__name__)

_MARKER_TO_LANGUAGE: dict[str, Language] = {
    "pyproject.toml": Language.PYTHON,
    "setup.py": Language.PYTHON,
    "setup.cfg": Language.PYTHON,
    "requirements.txt": Language.PYTHON,
    "go.mod": Language.GO,
    "go.work": Language.GO,
    "tsconfig.json": Language.TYPESCRIPT,
    "package.json": Language.TYPESCRIPT,
    "jsconfig.json": Language.TYPESCRIPT,
    "CMakeLists.txt": Language.CPP,
    "compile_commands.json": Language.CPP,
    ".clangd": Language.CPP,
}

_EXCLUDE_DIRS: set[str] = {
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "vendor",
    "dist",
    ".git",
    ".hg",
    ".svn",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "build",
    "target",
}


class SubProjectRegistry:
    """Discovers and resolves sub-project boundaries within workspaces."""

    def __init__(self) -> None:
        self._sub_projects: list[SubProject] = []
        self._workspace_roots: set[Path] = set()
        self._lock = asyncio.Lock()

    async def scan(self, workspace_root: Path, max_depth: int = 6) -> list[SubProject]:
        async with self._lock:
            return self._scan_locked(workspace_root, max_depth)

    async def rescan(self, workspace_root: Path) -> list[SubProject]:
        async with self._lock:
            workspace_root = workspace_root.resolve()
            self._sub_projects = [
                sp for sp in self._sub_projects if not sp.root.is_relative_to(workspace_root)
            ]
            return self._scan_locked(workspace_root)

    def _scan_locked(self, workspace_root: Path, max_depth: int = 6) -> list[SubProject]:
        workspace_root = workspace_root.resolve()
        self._workspace_roots.add(workspace_root)

        overrides = load_codebrain_overrides(workspace_root)
        exclude_paths = set(overrides.get("exclude", {}).get("paths", []))
        scan_depth = overrides.get("scan", {}).get("max_depth", max_depth)

        discovered: list[SubProject] = []
        self._scan_dir(
            workspace_root,
            workspace_root,
            scan_depth,
            0,
            exclude_paths,
            discovered,
        )
        self._assign_parents(discovered)

        existing_roots = {sp.root for sp in self._sub_projects}
        for sp in discovered:
            if sp.root not in existing_roots:
                self._sub_projects.append(sp)

        self._sub_projects.sort(key=lambda sp: len(sp.root.parts), reverse=True)

        logger.info("Scanned %s: found %d sub-projects", workspace_root, len(discovered))
        return list(discovered)

    def resolve(self, file_path: Path) -> SubProject | None:
        try:
            file_path = file_path.resolve()
        except OSError:
            pass

        sub_projects = self._sub_projects

        for sp in sub_projects:
            try:
                if file_path.is_relative_to(sp.root):
                    return sp
            except ValueError:
                continue

        return self._walkup_discover(file_path)

    def _walkup_discover(self, file_path: Path) -> SubProject | None:
        current = file_path if file_path.is_dir() else file_path.parent

        for _ in range(20):
            markers: dict[str, Path] = {}
            languages: set[Language] = set()

            try:
                for entry in current.iterdir():
                    if entry.name in _MARKER_TO_LANGUAGE and entry.is_file():
                        markers[entry.name] = entry
                        languages.add(_MARKER_TO_LANGUAGE[entry.name])
            except OSError:
                pass

            if markers:
                lang_list = sorted(languages, key=lambda lang: lang.value)
                toolchain = detect_toolchain(current, [lang.value for lang in lang_list])
                sp = SubProject(
                    root=current,
                    languages=lang_list,
                    markers=markers,
                    toolchain=toolchain,
                )
                # Atomic reference swap — no lock needed
                updated = self._sub_projects + [sp]
                updated.sort(key=lambda s: len(s.root.parts), reverse=True)
                self._sub_projects = updated
                return sp

            if current.parent == current:
                break
            current = current.parent

        return None

    def _scan_dir(
        self,
        workspace_root: Path,
        directory: Path,
        max_depth: int,
        current_depth: int,
        exclude_paths: set[str],
        discovered: list[SubProject],
    ) -> None:
        if current_depth > max_depth:
            return

        markers: dict[str, Path] = {}
        languages: set[Language] = set()
        subdirs: list[Path] = []

        try:
            for entry in sorted(directory.iterdir()):
                name = entry.name

                if entry.is_dir():
                    if name in _EXCLUDE_DIRS or name.startswith("."):
                        continue
                    try:
                        rel = str(entry.relative_to(workspace_root))
                        if any(rel.startswith(ex.rstrip("/")) for ex in exclude_paths):
                            continue
                    except ValueError:
                        pass
                    subdirs.append(entry)

                elif entry.is_file() and name in _MARKER_TO_LANGUAGE:
                    markers[name] = entry
                    languages.add(_MARKER_TO_LANGUAGE[name])
        except OSError:
            return

        if markers and directory != workspace_root:
            lang_list = sorted(languages, key=lambda lang: lang.value)
            toolchain = detect_toolchain(directory, [lang.value for lang in lang_list])
            sp = SubProject(
                root=directory,
                languages=lang_list,
                markers=markers,
                toolchain=toolchain,
            )
            discovered.append(sp)

        for subdir in subdirs:
            self._scan_dir(
                workspace_root,
                subdir,
                max_depth,
                current_depth + 1,
                exclude_paths,
                discovered,
            )

    def _assign_parents(self, sub_projects: list[SubProject]) -> None:
        by_depth = sorted(sub_projects, key=lambda sp: len(sp.root.parts))
        for i, sp in enumerate(by_depth):
            for j in range(i - 1, -1, -1):
                candidate = by_depth[j]
                try:
                    if sp.root.is_relative_to(candidate.root):
                        sp.parent = candidate.root
                        break
                except ValueError:
                    continue
