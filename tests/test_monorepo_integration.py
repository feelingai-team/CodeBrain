"""End-to-end monorepo workspace routing integration tests.

Tests the full flow: WorkspaceManager → SubProjectRegistry →
per-sub-project workspace creation with correct toolchain.
No real LSP servers are started — ws.start() is patched out.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from codebrain.core.models import Language
from codebrain.core.workspace import WorkspaceManager
from codebrain.fallback.chain import FallbackChain
from codebrain.lsp.servers.multi import MultiLanguageReporter


def _make_monorepo(tmp_path: Path) -> Path:
    """Create a monorepo fixture with Go, Python, and TypeScript sub-projects."""
    mono = tmp_path / "mono"
    mono.mkdir()
    (mono / ".git").mkdir()

    # Go backend
    backend = mono / "backend"
    backend.mkdir()
    (backend / "go.mod").write_text("module example.com/backend\n\ngo 1.21\n")
    (backend / "main.go").write_text("package main\n\nfunc main() {}\n")

    # Python ML service
    ml = mono / "ml-service"
    ml.mkdir()
    (ml / "pyproject.toml").write_text("[project]\nname = 'ml-service'\n")
    venv = ml / ".venv"
    venv.mkdir()
    (venv / "bin").mkdir()
    (venv / "bin" / "python").write_text("#!/bin/sh\n")
    (venv / "bin" / "python").chmod(0o755)
    (ml / "train.py").write_text("def train(): pass\n")

    # TypeScript frontend
    frontend = mono / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text('{"name": "frontend"}')
    (frontend / "tsconfig.json").write_text('{"compilerOptions": {}}')
    (frontend / "src").mkdir()
    (frontend / "src" / "app.ts").write_text("export const app = 'hello';\n")

    return mono


@pytest.fixture
def monorepo(tmp_path: Path) -> Path:
    return _make_monorepo(tmp_path)


class TestFullWorkspaceRouting:
    """Scenario 1: files in different sub-projects get different workspaces."""

    async def test_different_subprojects_get_different_workspaces(
        self, monorepo: Path
    ) -> None:
        manager = WorkspaceManager()
        await manager.registry.scan(monorepo)

        with patch("codebrain.core.workspace.Workspace.start", new_callable=AsyncMock):
            ws_go = await manager.get_workspace_for_file(monorepo / "backend" / "main.go")
            ws_py = await manager.get_workspace_for_file(monorepo / "ml-service" / "train.py")
            ws_ts = await manager.get_workspace_for_file(
                monorepo / "frontend" / "src" / "app.ts"
            )

        assert ws_go is not None
        assert ws_py is not None
        assert ws_ts is not None

        # Each sub-project gets its own workspace with a distinct root
        assert ws_go.info.root_path != ws_py.info.root_path
        assert ws_py.info.root_path != ws_ts.info.root_path
        assert ws_go.info.root_path != ws_ts.info.root_path

    async def test_go_workspace_has_correct_root(self, monorepo: Path) -> None:
        manager = WorkspaceManager()
        await manager.registry.scan(monorepo)

        with patch("codebrain.core.workspace.Workspace.start", new_callable=AsyncMock):
            ws = await manager.get_workspace_for_file(monorepo / "backend" / "main.go")

        assert ws is not None
        assert Path(ws.info.root_path) == (monorepo / "backend").resolve()

    async def test_python_workspace_has_correct_root(self, monorepo: Path) -> None:
        manager = WorkspaceManager()
        await manager.registry.scan(monorepo)

        with patch("codebrain.core.workspace.Workspace.start", new_callable=AsyncMock):
            ws = await manager.get_workspace_for_file(monorepo / "ml-service" / "train.py")

        assert ws is not None
        assert Path(ws.info.root_path) == (monorepo / "ml-service").resolve()

    async def test_typescript_workspace_has_correct_root(self, monorepo: Path) -> None:
        manager = WorkspaceManager()
        await manager.registry.scan(monorepo)

        with patch("codebrain.core.workspace.Workspace.start", new_callable=AsyncMock):
            ws = await manager.get_workspace_for_file(
                monorepo / "frontend" / "src" / "app.ts"
            )

        assert ws is not None
        assert Path(ws.info.root_path) == (monorepo / "frontend").resolve()

    async def test_each_workspace_has_correct_languages(self, monorepo: Path) -> None:
        manager = WorkspaceManager()
        await manager.registry.scan(monorepo)

        with patch("codebrain.core.workspace.Workspace.start", new_callable=AsyncMock):
            ws_go = await manager.get_workspace_for_file(monorepo / "backend" / "main.go")
            ws_py = await manager.get_workspace_for_file(monorepo / "ml-service" / "train.py")
            ws_ts = await manager.get_workspace_for_file(
                monorepo / "frontend" / "src" / "app.ts"
            )

        assert ws_go is not None and ws_py is not None and ws_ts is not None
        assert ws_go.info.languages is not None
        assert Language.GO.value in ws_go.info.languages

        assert ws_py.info.languages is not None
        assert Language.PYTHON.value in ws_py.info.languages

        assert ws_ts.info.languages is not None
        assert Language.TYPESCRIPT.value in ws_ts.info.languages

    async def test_python_workspace_has_python_env(self, monorepo: Path) -> None:
        manager = WorkspaceManager()
        await manager.registry.scan(monorepo)

        with patch("codebrain.core.workspace.Workspace.start", new_callable=AsyncMock):
            ws = await manager.get_workspace_for_file(monorepo / "ml-service" / "train.py")

        assert ws is not None

        # Retrieve the sub-project to inspect toolchain
        sp = manager.registry.resolve((monorepo / "ml-service" / "train.py").resolve())
        assert sp is not None
        assert sp.toolchain.python_env is not None
        assert sp.toolchain.python_env.venv_path == (monorepo / "ml-service" / ".venv").resolve()

    async def test_go_workspace_has_go_env(self, monorepo: Path) -> None:
        manager = WorkspaceManager()
        await manager.registry.scan(monorepo)

        sp = manager.registry.resolve((monorepo / "backend" / "main.go").resolve())
        assert sp is not None
        assert sp.toolchain.go_env is not None
        assert sp.toolchain.go_env.go_mod is not None


class TestSubProjectWorkspaceCaching:
    """Scenario 2: get_workspace_for_file returns the same object on repeated calls."""

    async def test_same_object_returned_for_same_file(self, monorepo: Path) -> None:
        manager = WorkspaceManager()
        await manager.registry.scan(monorepo)

        with patch("codebrain.core.workspace.Workspace.start", new_callable=AsyncMock):
            ws_first = await manager.get_workspace_for_file(
                monorepo / "ml-service" / "train.py"
            )
            ws_second = await manager.get_workspace_for_file(
                monorepo / "ml-service" / "train.py"
            )

        assert ws_first is not None
        assert ws_second is not None
        assert ws_first is ws_second

    async def test_same_object_for_different_files_same_subproject(
        self, monorepo: Path
    ) -> None:
        manager = WorkspaceManager()
        await manager.registry.scan(monorepo)

        # Create a second Python file in the same sub-project
        (monorepo / "ml-service" / "infer.py").write_text("def infer(): pass\n")

        with patch("codebrain.core.workspace.Workspace.start", new_callable=AsyncMock):
            ws_a = await manager.get_workspace_for_file(monorepo / "ml-service" / "train.py")
            ws_b = await manager.get_workspace_for_file(monorepo / "ml-service" / "infer.py")

        assert ws_a is not None and ws_b is not None
        assert ws_a is ws_b

    async def test_start_not_called_twice_when_already_running(
        self, monorepo: Path
    ) -> None:
        """start() is skipped on subsequent lookups when workspace is already running."""
        manager = WorkspaceManager()
        await manager.registry.scan(monorepo)

        async def _start_and_mark(ws_self: object) -> None:
            # Simulate what real start() does: mark the workspace as running
            object.__setattr__(ws_self, "_is_running", True)

        call_count = 0

        async def _mock_start(ws_self: object) -> None:
            nonlocal call_count
            call_count += 1
            object.__setattr__(ws_self, "_is_running", True)

        with patch("codebrain.core.workspace.Workspace.start", _mock_start):
            await manager.get_workspace_for_file(monorepo / "ml-service" / "train.py")
            await manager.get_workspace_for_file(monorepo / "ml-service" / "train.py")

        # start() is called exactly once because _is_running is True after first call
        assert call_count == 1


class TestFallbackChainWiring:
    """Scenario 3: Python workspaces have FallbackChain-wrapped reporters."""

    async def test_python_reporter_is_fallback_chain(self, monorepo: Path) -> None:
        manager = WorkspaceManager()
        await manager.registry.scan(monorepo)

        with patch("codebrain.core.workspace.Workspace.start", new_callable=AsyncMock):
            ws = await manager.get_workspace_for_file(monorepo / "ml-service" / "train.py")

        assert ws is not None
        assert isinstance(ws.reporter, MultiLanguageReporter)

        py_reporter = ws.reporter.get_reporter_for_file(Path("train.py"))
        assert py_reporter is not None
        assert isinstance(
            py_reporter, FallbackChain
        ), f"Expected FallbackChain, got {type(py_reporter).__name__}"

    async def test_fallback_chain_has_primary_reporter(self, monorepo: Path) -> None:
        manager = WorkspaceManager()
        await manager.registry.scan(monorepo)

        with patch("codebrain.core.workspace.Workspace.start", new_callable=AsyncMock):
            ws = await manager.get_workspace_for_file(monorepo / "ml-service" / "train.py")

        assert ws is not None
        py_reporter = ws.reporter.get_reporter_for_file(Path("train.py"))
        assert isinstance(py_reporter, FallbackChain)
        assert py_reporter.primary is not None

    async def test_go_reporter_has_fallback_chain(self, monorepo: Path) -> None:
        """Go has a CLI fallback (go vet), so reporter should be a FallbackChain."""
        manager = WorkspaceManager()
        await manager.registry.scan(monorepo)

        with patch("codebrain.core.workspace.Workspace.start", new_callable=AsyncMock):
            ws = await manager.get_workspace_for_file(monorepo / "backend" / "main.go")

        assert ws is not None
        go_reporter = ws.reporter.get_reporter_for_file(Path("main.go"))
        if go_reporter is not None:
            assert isinstance(go_reporter, FallbackChain)


class TestAutoDiscovery:
    """Scenario 4: auto-discovery without pre-registering the workspace."""

    async def test_autodiscovery_finds_subproject(self, monorepo: Path) -> None:
        """WorkspaceManager with no pre-registered root auto-discovers sub-projects."""
        manager = WorkspaceManager()
        # Do NOT call registry.scan() or add_workspace() — let auto_discover do it.

        with patch("codebrain.core.workspace.Workspace.start", new_callable=AsyncMock):
            ws = await manager.get_workspace_for_file(
                monorepo / "ml-service" / "train.py", auto_discover=True
            )

        assert ws is not None
        # The workspace root should be the sub-project root, not the monorepo root
        assert Path(ws.info.root_path) == (monorepo / "ml-service").resolve()

    async def test_autodiscovery_has_correct_languages(self, monorepo: Path) -> None:
        manager = WorkspaceManager()

        with patch("codebrain.core.workspace.Workspace.start", new_callable=AsyncMock):
            ws = await manager.get_workspace_for_file(
                monorepo / "backend" / "main.go", auto_discover=True
            )

        assert ws is not None
        assert ws.info.languages is not None
        assert Language.GO.value in ws.info.languages

    async def test_autodiscovery_returns_none_for_unknown_path(
        self, tmp_path: Path
    ) -> None:
        """A file with no markers and no parent workspace returns None."""
        manager = WorkspaceManager()
        unknown = tmp_path / "orphan" / "file.txt"
        unknown.parent.mkdir(parents=True)
        unknown.write_text("hello")

        ws = await manager.get_workspace_for_file(unknown, auto_discover=True)
        assert ws is None

    async def test_autodiscovery_registries_subprojects_after_scan(
        self, monorepo: Path
    ) -> None:
        """After auto-discovery, the registry has sub-projects for the monorepo."""
        manager = WorkspaceManager()

        with patch("codebrain.core.workspace.Workspace.start", new_callable=AsyncMock):
            await manager.get_workspace_for_file(
                monorepo / "frontend" / "src" / "app.ts", auto_discover=True
            )

        # Registry should now know about at least the frontend sub-project
        sp = manager.registry.resolve((monorepo / "frontend" / "src" / "app.ts").resolve())
        assert sp is not None
        assert Language.TYPESCRIPT in sp.languages
