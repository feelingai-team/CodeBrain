"""Integration tests for LSP reporter stack (requires pyright-langserver)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from codebrain.core.models import DiagnosticSeverity, Position, Range
from codebrain.lsp.servers.base import (
    lsp_range_to_range,
    lsp_severity_to_severity,
    range_to_lsp_range,
    uri_to_path,
)
from codebrain.lsp.servers.multi import MultiLanguageReporter
from codebrain.lsp.servers.pyright import PyrightReporter

PYRIGHT_LANGSERVER_AVAILABLE = shutil.which("pyright-langserver") is not None

SAMPLE_WITH_ERROR = """\
x: int = "not an int"

def add(a: int, b: int) -> int:
    return a + b

def unused():
    pass

result = add(1, 2)
"""

SAMPLE_CLEAN = """\
x: int = 1
y: str = "hello"

def greet(name: str) -> str:
    return "Hello, " + name
"""


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Create a workspace with sample Python files."""
    (tmp_path / "error.py").write_text(SAMPLE_WITH_ERROR)
    (tmp_path / "clean.py").write_text(SAMPLE_CLEAN)
    (tmp_path / "pyrightconfig.json").write_text(
        '{"include": ["error.py", "clean.py"]}'
    )
    return tmp_path


# -- Utility function tests (no server needed) --


class TestUtilityFunctions:
    def test_uri_to_path(self) -> None:
        path = uri_to_path("file:///home/user/project/test.py")
        assert path == Path("/home/user/project/test.py")

    def test_uri_to_path_with_encoded_spaces(self) -> None:
        path = uri_to_path("file:///home/user/my%20project/test.py")
        assert path == Path("/home/user/my project/test.py")

    def test_lsp_range_to_range(self) -> None:
        from lsprotocol import types as lsp

        lsp_r = lsp.Range(
            start=lsp.Position(line=1, character=5),
            end=lsp.Position(line=1, character=10),
        )
        r = lsp_range_to_range(lsp_r)
        assert r.start.line == 1
        assert r.start.character == 5
        assert r.end.line == 1
        assert r.end.character == 10

    def test_range_to_lsp_range(self) -> None:
        r = Range(
            start=Position(line=3, character=0),
            end=Position(line=3, character=8),
        )
        lsp_r = range_to_lsp_range(r)
        assert lsp_r.start.line == 3
        assert lsp_r.start.character == 0
        assert lsp_r.end.line == 3
        assert lsp_r.end.character == 8

    def test_range_roundtrip(self) -> None:
        r = Range(
            start=Position(line=10, character=20),
            end=Position(line=15, character=0),
        )
        lsp_r = range_to_lsp_range(r)
        r2 = lsp_range_to_range(lsp_r)
        assert r == r2

    def test_lsp_severity_to_severity(self) -> None:
        from lsprotocol import types as lsp

        sev = lsp_severity_to_severity
        assert sev(lsp.DiagnosticSeverity.Error) == DiagnosticSeverity.ERROR
        assert sev(lsp.DiagnosticSeverity.Warning) == DiagnosticSeverity.WARNING
        assert sev(lsp.DiagnosticSeverity.Information) == DiagnosticSeverity.INFORMATION
        assert sev(lsp.DiagnosticSeverity.Hint) == DiagnosticSeverity.HINT
        assert sev(None) == DiagnosticSeverity.ERROR


# -- MultiLanguageReporter unit tests (no server needed) --


class TestMultiLanguageReporter:
    def test_empty_reporter(self, tmp_path: Path) -> None:
        multi = MultiLanguageReporter(tmp_path)
        assert multi.name == "multi-language"
        assert multi.supported_extensions == set()
        assert not multi.is_running

    def test_add_reporter(self, tmp_path: Path) -> None:
        pyright = PyrightReporter(tmp_path)
        multi = MultiLanguageReporter(tmp_path, reporters=[pyright])
        assert ".py" in multi.supported_extensions
        assert ".pyi" in multi.supported_extensions

    def test_get_reporter_for_file(self, tmp_path: Path) -> None:
        pyright = PyrightReporter(tmp_path)
        multi = MultiLanguageReporter(tmp_path, reporters=[pyright])
        assert multi.get_reporter_for_file(Path("test.py")) is pyright
        assert multi.get_reporter_for_file(Path("test.rs")) is None

    def test_duplicate_extension_raises(self, tmp_path: Path) -> None:
        pyright1 = PyrightReporter(tmp_path)
        pyright2 = PyrightReporter(tmp_path)
        multi = MultiLanguageReporter(tmp_path, reporters=[pyright1])
        with pytest.raises(ValueError, match="already handled"):
            multi.add_reporter(pyright2)

    async def test_get_diagnostics_no_reporter(self, tmp_path: Path) -> None:
        multi = MultiLanguageReporter(tmp_path)
        diags = await multi.get_diagnostics(Path("test.rs"))
        assert diags == []


# -- Pyright reporter integration tests --


@pytest.mark.skipif(
    not PYRIGHT_LANGSERVER_AVAILABLE, reason="pyright-langserver not installed"
)
class TestPyrightReporterIntegration:
    async def test_start_stop(self, workspace: Path) -> None:
        reporter = PyrightReporter(workspace)
        assert not reporter.is_running
        await reporter.start()
        assert reporter.is_running
        await reporter.stop()
        assert not reporter.is_running

    async def test_get_diagnostics_with_errors(self, workspace: Path) -> None:
        reporter = PyrightReporter(workspace)
        try:
            await reporter.start()
            diags = await reporter.get_diagnostics(workspace / "error.py")
            assert len(diags) > 0
            assert any(d.severity == DiagnosticSeverity.ERROR for d in diags)
        finally:
            await reporter.stop()

    async def test_get_diagnostics_clean(self, workspace: Path) -> None:
        reporter = PyrightReporter(workspace)
        try:
            await reporter.start()
            diags = await reporter.get_diagnostics(workspace / "clean.py")
            errors = [d for d in diags if d.severity == DiagnosticSeverity.ERROR]
            assert errors == []
        finally:
            await reporter.stop()

    async def test_get_context(self, workspace: Path) -> None:
        reporter = PyrightReporter(workspace)
        try:
            await reporter.start()
            diags = await reporter.get_diagnostics(workspace / "error.py")
            if diags:
                ctx = await reporter.get_context(diags[0])
                assert ctx.diagnostic == diags[0]
                # Context should have been populated
                assert ctx.reference_depth >= 1
        finally:
            await reporter.stop()

    async def test_open_close_file(self, workspace: Path) -> None:
        reporter = PyrightReporter(workspace)
        try:
            await reporter.start()
            file_path = workspace / "clean.py"
            await reporter.open_file(file_path)
            assert file_path in reporter._open_files
            await reporter.close_file(file_path)
            assert file_path not in reporter._open_files
        finally:
            await reporter.stop()

    async def test_update_file(self, workspace: Path) -> None:
        reporter = PyrightReporter(workspace)
        try:
            await reporter.start()
            file_path = workspace / "clean.py"
            await reporter.open_file(file_path)
            # Update to content with an error
            await reporter.update_file(file_path, 'x: int = "bad"\n')
            # File version should have incremented
            assert reporter._file_versions[file_path] == 2
        finally:
            await reporter.stop()


@pytest.mark.skipif(
    not PYRIGHT_LANGSERVER_AVAILABLE, reason="pyright-langserver not installed"
)
class TestMultiReporterIntegration:
    async def test_routing_diagnostics(self, workspace: Path) -> None:
        pyright = PyrightReporter(workspace)
        multi = MultiLanguageReporter(workspace, reporters=[pyright])
        try:
            await multi.start()
            assert multi.is_running
            diags = await multi.get_diagnostics(workspace / "error.py")
            assert len(diags) > 0
        finally:
            await multi.stop()

    async def test_no_reporter_for_unknown_ext(self, workspace: Path) -> None:
        pyright = PyrightReporter(workspace)
        multi = MultiLanguageReporter(workspace, reporters=[pyright])
        try:
            await multi.start()
            diags = await multi.get_diagnostics(workspace / "test.rs")
            assert diags == []
        finally:
            await multi.stop()
