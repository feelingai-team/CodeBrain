"""Tests for SubProjectRegistry — sub-project discovery and resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from codebrain.core.models import Language
from codebrain.core.registry import SubProjectRegistry


def _make_monorepo(tmp_path: Path) -> Path:
    """Create a monorepo-like directory tree for testing.

    Structure:
        mono/
        ├── .git/
        ├── backend/
        │   ├── go.mod
        │   └── ml/
        │       └── pyproject.toml
        ├── frontend/
        │   ├── package.json
        │   └── tsconfig.json
        ├── shared/
        │   └── pyproject.toml
        └── legacy/
            └── setup.py
    """
    mono = tmp_path / "mono"
    mono.mkdir()
    (mono / ".git").mkdir()

    backend = mono / "backend"
    backend.mkdir()
    (backend / "go.mod").write_text("module example.com/backend\n\ngo 1.21\n")

    ml = backend / "ml"
    ml.mkdir()
    (ml / "pyproject.toml").write_text("[project]\nname = 'ml'\n")

    frontend = mono / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text("{}")
    (frontend / "tsconfig.json").write_text("{}")

    shared = mono / "shared"
    shared.mkdir()
    (shared / "pyproject.toml").write_text("[project]\nname = 'shared'\n")

    legacy = mono / "legacy"
    legacy.mkdir()
    (legacy / "setup.py").write_text("from setuptools import setup\nsetup()")

    return mono


class TestScan:
    @pytest.mark.asyncio
    async def test_finds_sub_projects(self, tmp_path: Path) -> None:
        mono = _make_monorepo(tmp_path)
        registry = SubProjectRegistry()
        sub_projects = await registry.scan(mono)

        roots = {sp.root for sp in sub_projects}
        assert mono / "backend" in roots
        assert mono / "backend" / "ml" in roots
        assert mono / "frontend" in roots
        assert mono / "shared" in roots

    @pytest.mark.asyncio
    async def test_detects_languages(self, tmp_path: Path) -> None:
        mono = _make_monorepo(tmp_path)
        registry = SubProjectRegistry()
        await registry.scan(mono)

        backend = registry.resolve(mono / "backend" / "main.go")
        assert backend is not None
        assert Language.GO in backend.languages

        ml = registry.resolve(mono / "backend" / "ml" / "train.py")
        assert ml is not None
        assert Language.PYTHON in ml.languages

    @pytest.mark.asyncio
    async def test_respects_max_depth(self, tmp_path: Path) -> None:
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        (deep / "go.mod").write_text("module deep\n\ngo 1.21\n")

        registry = SubProjectRegistry()
        sps = await registry.scan(tmp_path, max_depth=2)
        roots = {sp.root for sp in sps}
        assert deep not in roots

        registry2 = SubProjectRegistry()
        sps2 = await registry2.scan(tmp_path, max_depth=4)
        roots2 = {sp.root for sp in sps2}
        assert deep in roots2

    @pytest.mark.asyncio
    async def test_skips_excluded_dirs(self, tmp_path: Path) -> None:
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "package.json").write_text("{}")
        (tmp_path / ".venv").mkdir()
        (tmp_path / ".venv" / "pyproject.toml").write_text("")

        registry = SubProjectRegistry()
        sps = await registry.scan(tmp_path)
        roots = {sp.root for sp in sps}
        assert tmp_path / "node_modules" not in roots
        assert tmp_path / ".venv" not in roots


class TestResolve:
    @pytest.mark.asyncio
    async def test_deepest_match(self, tmp_path: Path) -> None:
        mono = _make_monorepo(tmp_path)
        registry = SubProjectRegistry()
        await registry.scan(mono)

        sp = registry.resolve(mono / "backend" / "ml" / "model.py")
        assert sp is not None
        assert sp.root == mono / "backend" / "ml"

    @pytest.mark.asyncio
    async def test_parent_match(self, tmp_path: Path) -> None:
        mono = _make_monorepo(tmp_path)
        registry = SubProjectRegistry()
        await registry.scan(mono)

        sp = registry.resolve(mono / "backend" / "main.go")
        assert sp is not None
        assert sp.root == mono / "backend"

    @pytest.mark.asyncio
    async def test_no_match(self, tmp_path: Path) -> None:
        registry = SubProjectRegistry()
        sp = registry.resolve(tmp_path / "random" / "file.txt")
        assert sp is None

    @pytest.mark.asyncio
    async def test_walkup_fallback(self, tmp_path: Path) -> None:
        proj = tmp_path / "new_project"
        proj.mkdir()
        (proj / "go.mod").write_text("module new\n\ngo 1.21\n")

        registry = SubProjectRegistry()
        sp = registry.resolve(proj / "main.go")
        assert sp is not None
        assert sp.root == proj


class TestRescan:
    @pytest.mark.asyncio
    async def test_picks_up_new_subproject(self, tmp_path: Path) -> None:
        mono = _make_monorepo(tmp_path)
        registry = SubProjectRegistry()
        await registry.scan(mono)

        new = mono / "new_service"
        new.mkdir()
        (new / "go.mod").write_text("module new\n\ngo 1.21\n")

        await registry.rescan(mono)

        sp = registry.resolve(mono / "new_service" / "main.go")
        assert sp is not None
        assert sp.root == new


class TestNestedParent:
    @pytest.mark.asyncio
    async def test_parent_field_set(self, tmp_path: Path) -> None:
        mono = _make_monorepo(tmp_path)
        registry = SubProjectRegistry()
        await registry.scan(mono)

        ml = registry.resolve(mono / "backend" / "ml" / "x.py")
        assert ml is not None
        assert ml.parent == mono / "backend"
