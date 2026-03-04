"""Tests for Pyright CLI fallback reporter."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from codebrain.core.models import DiagnosticSeverity
from codebrain.fallback.pyright_cli import PYRIGHT_SEVERITY_MAP, PyrightCLIReporter

PYRIGHT_AVAILABLE = shutil.which("pyright") is not None

SAMPLE_WITH_ERROR = """\
x: int = "not an int"
y: str = 42
"""

SAMPLE_CLEAN = """\
x: int = 1
y: str = "hello"
"""


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Create a workspace with sample Python files."""
    (tmp_path / "error.py").write_text(SAMPLE_WITH_ERROR)
    (tmp_path / "clean.py").write_text(SAMPLE_CLEAN)
    # Minimal pyright config so it only checks our files
    (tmp_path / "pyrightconfig.json").write_text(
        '{"include": ["error.py", "clean.py"], "reportMissingModuleSource": false}'
    )
    return tmp_path


class TestSeverityMap:
    def test_all_severities_mapped(self) -> None:
        assert "error" in PYRIGHT_SEVERITY_MAP
        assert "warning" in PYRIGHT_SEVERITY_MAP
        assert "information" in PYRIGHT_SEVERITY_MAP
        assert "hint" in PYRIGHT_SEVERITY_MAP

    def test_severity_values(self) -> None:
        assert PYRIGHT_SEVERITY_MAP["error"] == DiagnosticSeverity.ERROR
        assert PYRIGHT_SEVERITY_MAP["warning"] == DiagnosticSeverity.WARNING
        assert PYRIGHT_SEVERITY_MAP["information"] == DiagnosticSeverity.INFORMATION
        assert PYRIGHT_SEVERITY_MAP["hint"] == DiagnosticSeverity.HINT


class TestPyrightCLIReporter:
    def test_properties(self, tmp_path: Path) -> None:
        reporter = PyrightCLIReporter(tmp_path)
        assert reporter.name == "pyright-cli"
        assert ".py" in reporter.supported_extensions
        assert ".pyi" in reporter.supported_extensions

    def test_custom_timeout(self, tmp_path: Path) -> None:
        reporter = PyrightCLIReporter(tmp_path, timeout=30.0)
        assert reporter._timeout == 30.0

    def test_default_timeout(self, tmp_path: Path) -> None:
        reporter = PyrightCLIReporter(tmp_path)
        assert reporter._timeout == PyrightCLIReporter.DEFAULT_TIMEOUT


class TestParseOutput:
    def test_parse_diagnostics(self, tmp_path: Path) -> None:
        reporter = PyrightCLIReporter(tmp_path)
        output = {
            "generalDiagnostics": [
                {
                    "file": str(tmp_path / "test.py"),
                    "severity": "error",
                    "message": "Type mismatch",
                    "range": {
                        "start": {"line": 0, "character": 9},
                        "end": {"line": 0, "character": 22},
                    },
                    "rule": "reportAssignmentType",
                },
            ],
        }
        results = reporter._parse_output(output)
        assert len(results) == 1
        diags = list(results.values())[0]
        assert len(diags) == 1
        assert diags[0].severity == DiagnosticSeverity.ERROR
        assert diags[0].message == "Type mismatch"
        assert diags[0].source == "pyright"
        assert diags[0].code == "reportAssignmentType"
        assert diags[0].range.start.line == 0
        assert diags[0].range.start.character == 9

    def test_parse_empty_output(self, tmp_path: Path) -> None:
        reporter = PyrightCLIReporter(tmp_path)
        results = reporter._parse_output({"generalDiagnostics": []})
        assert results == {}

    def test_parse_relative_path(self, tmp_path: Path) -> None:
        reporter = PyrightCLIReporter(tmp_path)
        output = {
            "generalDiagnostics": [
                {
                    "file": "test.py",
                    "severity": "warning",
                    "message": "Unused import",
                    "range": {
                        "start": {"line": 0, "character": 0},
                        "end": {"line": 0, "character": 10},
                    },
                },
            ],
        }
        results = reporter._parse_output(output)
        assert len(results) == 1
        key = list(results.keys())[0]
        assert key.is_absolute()

    def test_parse_missing_fields(self, tmp_path: Path) -> None:
        reporter = PyrightCLIReporter(tmp_path)
        output = {
            "generalDiagnostics": [
                {
                    "file": str(tmp_path / "test.py"),
                    "message": "Some error",
                    # Missing severity, range, rule
                },
            ],
        }
        results = reporter._parse_output(output)
        diags = list(results.values())[0]
        assert diags[0].severity == DiagnosticSeverity.ERROR  # default
        assert diags[0].range.start.line == 0  # default

    def test_parse_skips_missing_file(self, tmp_path: Path) -> None:
        reporter = PyrightCLIReporter(tmp_path)
        output = {
            "generalDiagnostics": [
                {"message": "No file field"},
            ],
        }
        results = reporter._parse_output(output)
        assert results == {}

    def test_parse_multiple_files(self, tmp_path: Path) -> None:
        reporter = PyrightCLIReporter(tmp_path)
        output = {
            "generalDiagnostics": [
                {
                    "file": str(tmp_path / "a.py"),
                    "severity": "error",
                    "message": "Error in a",
                    "range": {
                        "start": {"line": 0, "character": 0},
                        "end": {"line": 0, "character": 5},
                    },
                },
                {
                    "file": str(tmp_path / "b.py"),
                    "severity": "warning",
                    "message": "Warning in b",
                    "range": {
                        "start": {"line": 1, "character": 0},
                        "end": {"line": 1, "character": 5},
                    },
                },
                {
                    "file": str(tmp_path / "a.py"),
                    "severity": "error",
                    "message": "Another error in a",
                    "range": {
                        "start": {"line": 2, "character": 0},
                        "end": {"line": 2, "character": 5},
                    },
                },
            ],
        }
        results = reporter._parse_output(output)
        assert len(results) == 2
        assert len(results[tmp_path / "a.py"]) == 2
        assert len(results[tmp_path / "b.py"]) == 1


@pytest.mark.skipif(not PYRIGHT_AVAILABLE, reason="pyright not installed")
class TestPyrightCLIIntegration:
    async def test_file_with_errors(self, workspace: Path) -> None:
        reporter = PyrightCLIReporter(workspace)
        diags = await reporter.get_diagnostics(workspace / "error.py")
        assert len(diags) > 0
        assert all(d.source == "pyright" for d in diags)

    async def test_clean_file(self, workspace: Path) -> None:
        reporter = PyrightCLIReporter(workspace)
        diags = await reporter.get_diagnostics(workspace / "clean.py")
        # Clean file should have no error-level diagnostics
        errors = [d for d in diags if d.severity == DiagnosticSeverity.ERROR]
        assert errors == []

    async def test_workspace_diagnostics(self, workspace: Path) -> None:
        reporter = PyrightCLIReporter(workspace)
        results = await reporter.get_all_diagnostics()
        # Should find diagnostics for the error file
        found_errors = False
        for path, diags in results.items():
            if "error" in str(path):
                found_errors = len(diags) > 0
        assert found_errors

    async def test_not_found_pyright(self, tmp_path: Path) -> None:
        reporter = PyrightCLIReporter(tmp_path, pyright_path="/nonexistent/pyright")
        diags = await reporter.get_diagnostics(tmp_path / "test.py")
        assert diags == []
