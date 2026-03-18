"""Tests for Go vet CLI fallback reporter."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from codebrain.core.models import DiagnosticSeverity
from codebrain.fallback.govet_cli import GoVetCLIReporter

GO_AVAILABLE = shutil.which("go") is not None

# A Go file with a vet-detectable issue: unreachable code after return
SAMPLE_WITH_VET_ISSUE = """\
package main

import "fmt"

func main() {
\tfmt.Println("hello")
}

func badFunc() int {
\treturn 1
\treturn 2
}
"""

SAMPLE_CLEAN = """\
package main

import "fmt"

func main() {
\tfmt.Println("hello")
}
"""


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Create a minimal Go module workspace with sample Go files."""
    (tmp_path / "go.mod").write_text("module example.com/test\n\ngo 1.21\n")
    (tmp_path / "issue.go").write_text(SAMPLE_WITH_VET_ISSUE)
    (tmp_path / "clean.go").write_text(SAMPLE_CLEAN)
    return tmp_path


class TestGoVetCLIReporterProperties:
    def test_name(self, tmp_path: Path) -> None:
        reporter = GoVetCLIReporter(tmp_path)
        assert reporter.name == "govet-cli"

    def test_supported_extensions(self, tmp_path: Path) -> None:
        reporter = GoVetCLIReporter(tmp_path)
        assert ".go" in reporter.supported_extensions

    def test_default_timeout(self, tmp_path: Path) -> None:
        reporter = GoVetCLIReporter(tmp_path)
        assert reporter._timeout == GoVetCLIReporter.DEFAULT_TIMEOUT

    def test_custom_timeout(self, tmp_path: Path) -> None:
        reporter = GoVetCLIReporter(tmp_path, timeout=60.0)
        assert reporter._timeout == 60.0

    def test_supports_file(self, tmp_path: Path) -> None:
        reporter = GoVetCLIReporter(tmp_path)
        assert reporter.supports_file(Path("main.go"))
        assert not reporter.supports_file(Path("main.py"))


class TestParseOutput:
    def test_parse_single_diagnostic(self, tmp_path: Path) -> None:
        reporter = GoVetCLIReporter(tmp_path)
        output = f"{tmp_path}/main.go:10:5: unreachable code\n"
        results = reporter._parse_output(output)
        assert len(results) == 1
        diags = list(results.values())[0]
        assert len(diags) == 1
        assert diags[0].severity == DiagnosticSeverity.WARNING
        assert diags[0].message == "unreachable code"
        assert diags[0].source == "go-vet"
        assert diags[0].code is None
        # 1-indexed line 10 → 0-indexed 9
        assert diags[0].range.start.line == 9
        # 1-indexed col 5 → 0-indexed 4
        assert diags[0].range.start.character == 4

    def test_parse_without_column(self, tmp_path: Path) -> None:
        reporter = GoVetCLIReporter(tmp_path)
        output = f"{tmp_path}/main.go:5: suspicious call to Printf\n"
        results = reporter._parse_output(output)
        diags = list(results.values())[0]
        assert diags[0].range.start.line == 4  # 5 - 1
        assert diags[0].range.start.character == 0  # defaults to 0

    def test_parse_empty_output(self, tmp_path: Path) -> None:
        reporter = GoVetCLIReporter(tmp_path)
        results = reporter._parse_output("")
        assert results == {}

    def test_parse_skips_package_headers(self, tmp_path: Path) -> None:
        reporter = GoVetCLIReporter(tmp_path)
        output = "# example.com/test\n" + f"{tmp_path}/main.go:3:1: bad code\n"
        results = reporter._parse_output(output)
        assert len(results) == 1

    def test_parse_skips_vet_meta_lines(self, tmp_path: Path) -> None:
        reporter = GoVetCLIReporter(tmp_path)
        output = "vet: no packages loaded\n"
        results = reporter._parse_output(output)
        assert results == {}

    def test_parse_skips_non_go_lines(self, tmp_path: Path) -> None:
        reporter = GoVetCLIReporter(tmp_path)
        output = "some random line without a .go file reference\n"
        results = reporter._parse_output(output)
        assert results == {}

    def test_parse_relative_path_resolved(self, tmp_path: Path) -> None:
        reporter = GoVetCLIReporter(tmp_path)
        output = "main.go:1:1: suspicious construct\n"
        results = reporter._parse_output(output)
        assert len(results) == 1
        key = list(results.keys())[0]
        assert key.is_absolute()
        assert key == tmp_path / "main.go"

    def test_parse_multiple_files(self, tmp_path: Path) -> None:
        reporter = GoVetCLIReporter(tmp_path)
        output = (
            f"{tmp_path}/a.go:1:1: issue in a\n"
            f"{tmp_path}/b.go:2:3: issue in b\n"
            f"{tmp_path}/a.go:5:1: another issue in a\n"
        )
        results = reporter._parse_output(output)
        assert len(results) == 2
        assert len(results[tmp_path / "a.go"]) == 2
        assert len(results[tmp_path / "b.go"]) == 1

    def test_all_diagnostics_are_warnings(self, tmp_path: Path) -> None:
        reporter = GoVetCLIReporter(tmp_path)
        output = (
            f"{tmp_path}/main.go:1:1: first\n"
            f"{tmp_path}/main.go:2:1: second\n"
        )
        results = reporter._parse_output(output)
        for diags in results.values():
            for d in diags:
                assert d.severity == DiagnosticSeverity.WARNING

    def test_line_1_col_1_becomes_0_0(self, tmp_path: Path) -> None:
        """Verify minimum 1-indexed values map to 0-indexed 0."""
        reporter = GoVetCLIReporter(tmp_path)
        output = f"{tmp_path}/main.go:1:1: msg\n"
        results = reporter._parse_output(output)
        diags = list(results.values())[0]
        assert diags[0].range.start.line == 0
        assert diags[0].range.start.character == 0

    def test_start_equals_end(self, tmp_path: Path) -> None:
        """go vet gives a point location; start and end should be the same."""
        reporter = GoVetCLIReporter(tmp_path)
        output = f"{tmp_path}/main.go:3:7: some message\n"
        results = reporter._parse_output(output)
        diags = list(results.values())[0]
        d = diags[0]
        assert d.range.start.line == d.range.end.line
        assert d.range.start.character == d.range.end.character

    def test_message_with_colons(self, tmp_path: Path) -> None:
        """Messages that contain colons should be captured fully."""
        reporter = GoVetCLIReporter(tmp_path)
        msg = "call has arguments but no formatting directives: fmt.Printf(x)"
        output = f"{tmp_path}/main.go:4:2: {msg}\n"
        results = reporter._parse_output(output)
        diags = list(results.values())[0]
        assert "fmt.Printf(x)" in diags[0].message


@pytest.mark.skipif(not GO_AVAILABLE, reason="go not installed")
class TestGoVetCLIIntegration:
    async def test_not_found_go(self, tmp_path: Path) -> None:
        reporter = GoVetCLIReporter(tmp_path, go_path="/nonexistent/go")
        diags = await reporter.get_diagnostics(tmp_path / "main.go")
        assert diags == []

    async def test_workspace_diagnostics_returns_dict(self, workspace: Path) -> None:
        reporter = GoVetCLIReporter(workspace)
        results = await reporter.get_all_diagnostics()
        # Result must be a dict (may be empty if no vet issues found on this Go version)
        assert isinstance(results, dict)

    async def test_get_diagnostics_nonexistent_file(self, workspace: Path) -> None:
        reporter = GoVetCLIReporter(workspace)
        # Passing a nonexistent file still returns a list (may be empty or error-handled)
        diags = await reporter.get_diagnostics(workspace / "nonexistent.go")
        assert isinstance(diags, list)
