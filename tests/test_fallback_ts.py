"""Tests for tsc CLI fallback reporter."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from codebrain.core.models import DiagnosticSeverity
from codebrain.fallback.tsc_cli import TscCLIReporter

TSC_AVAILABLE = shutil.which("tsc") is not None

# A TypeScript file with a type error
SAMPLE_WITH_ERROR = """\
const x: number = "not a number";
const y: string = 42;
"""

SAMPLE_CLEAN = """\
const cleanNum: number = 1;
const cleanStr: string = "hello";
"""


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Create a minimal TypeScript workspace with sample TS files."""
    (tmp_path / "error.ts").write_text(SAMPLE_WITH_ERROR)
    (tmp_path / "clean.ts").write_text(SAMPLE_CLEAN)
    (tmp_path / "tsconfig.json").write_text(
        '{"compilerOptions": {"strict": true, "noEmit": true}, "include": ["*.ts"]}'
    )
    return tmp_path


@pytest.fixture
def workspace_no_tsconfig(tmp_path: Path) -> Path:
    """Create a TypeScript workspace WITHOUT tsconfig.json."""
    (tmp_path / "error.ts").write_text(SAMPLE_WITH_ERROR)
    (tmp_path / "clean.ts").write_text(SAMPLE_CLEAN)
    return tmp_path


class TestTscCLIReporterProperties:
    def test_name(self, tmp_path: Path) -> None:
        reporter = TscCLIReporter(tmp_path)
        assert reporter.name == "tsc-cli"

    def test_supported_extensions(self, tmp_path: Path) -> None:
        reporter = TscCLIReporter(tmp_path)
        assert ".ts" in reporter.supported_extensions
        assert ".tsx" in reporter.supported_extensions
        assert ".js" in reporter.supported_extensions
        assert ".jsx" in reporter.supported_extensions

    def test_default_timeout(self, tmp_path: Path) -> None:
        reporter = TscCLIReporter(tmp_path)
        assert reporter._timeout == TscCLIReporter.DEFAULT_TIMEOUT

    def test_custom_timeout(self, tmp_path: Path) -> None:
        reporter = TscCLIReporter(tmp_path, timeout=60.0)
        assert reporter._timeout == 60.0

    def test_supports_file_ts(self, tmp_path: Path) -> None:
        reporter = TscCLIReporter(tmp_path)
        assert reporter.supports_file(Path("app.ts"))
        assert reporter.supports_file(Path("component.tsx"))
        assert reporter.supports_file(Path("util.js"))
        assert reporter.supports_file(Path("index.jsx"))

    def test_does_not_support_other_extensions(self, tmp_path: Path) -> None:
        reporter = TscCLIReporter(tmp_path)
        assert not reporter.supports_file(Path("main.py"))
        assert not reporter.supports_file(Path("main.go"))

    def test_tsconfig_path_stored(self, tmp_path: Path) -> None:
        config = tmp_path / "tsconfig.json"
        reporter = TscCLIReporter(tmp_path, tsconfig_path=config)
        assert reporter._tsconfig_path == config

    def test_tsconfig_path_default_none(self, tmp_path: Path) -> None:
        reporter = TscCLIReporter(tmp_path)
        assert reporter._tsconfig_path is None


class TestResolveTsconfig:
    def test_explicit_tsconfig_returned(self, tmp_path: Path) -> None:
        config = tmp_path / "custom-tsconfig.json"
        config.write_text("{}")
        reporter = TscCLIReporter(tmp_path, tsconfig_path=config)
        assert reporter._resolve_tsconfig() == config

    def test_auto_discovers_tsconfig_in_workspace(self, tmp_path: Path) -> None:
        tsconfig = tmp_path / "tsconfig.json"
        tsconfig.write_text("{}")
        reporter = TscCLIReporter(tmp_path)
        assert reporter._resolve_tsconfig() == tsconfig

    def test_returns_none_when_no_tsconfig(self, tmp_path: Path) -> None:
        reporter = TscCLIReporter(tmp_path)
        assert reporter._resolve_tsconfig() is None

    def test_explicit_takes_precedence_over_auto(self, tmp_path: Path) -> None:
        """Explicit tsconfig_path wins even when tsconfig.json exists in workspace."""
        (tmp_path / "tsconfig.json").write_text("{}")
        custom = tmp_path / "tsconfig.build.json"
        custom.write_text("{}")
        reporter = TscCLIReporter(tmp_path, tsconfig_path=custom)
        assert reporter._resolve_tsconfig() == custom


class TestRunTscNoTsconfig:
    async def test_get_all_diagnostics_returns_empty_without_tsconfig(
        self, tmp_path: Path
    ) -> None:
        """Without tsconfig and no files, _run_tsc returns {} instead of running bare tsc."""
        reporter = TscCLIReporter(tmp_path)
        results = await reporter.get_all_diagnostics()
        assert results == {}


class TestParseOutput:
    def test_parse_single_error(self, tmp_path: Path) -> None:
        reporter = TscCLIReporter(tmp_path)
        msg = "Type 'string' is not assignable to type 'number'."
        output = f"{tmp_path}/app.ts(10,5): error TS2322: {msg}\n"
        results = reporter._parse_output(output)
        assert len(results) == 1
        diags = list(results.values())[0]
        assert len(diags) == 1
        d = diags[0]
        assert d.severity == DiagnosticSeverity.ERROR
        assert d.message == "Type 'string' is not assignable to type 'number'."
        assert d.source == "tsc"
        assert d.code == "TS2322"
        # 1-indexed line 10 → 0-indexed 9
        assert d.range.start.line == 9
        # 1-indexed col 5 → 0-indexed 4
        assert d.range.start.character == 4

    def test_parse_warning(self, tmp_path: Path) -> None:
        reporter = TscCLIReporter(tmp_path)
        msg = "'x' is declared but its value is never read."
        output = f"{tmp_path}/app.ts(3,1): warning TS6133: {msg}\n"
        results = reporter._parse_output(output)
        diags = list(results.values())[0]
        assert diags[0].severity == DiagnosticSeverity.WARNING
        assert diags[0].code == "TS6133"

    def test_parse_empty_output(self, tmp_path: Path) -> None:
        reporter = TscCLIReporter(tmp_path)
        results = reporter._parse_output("")
        assert results == {}

    def test_parse_skips_non_matching_lines(self, tmp_path: Path) -> None:
        reporter = TscCLIReporter(tmp_path)
        output = "Found 2 errors in 1 file.\n"
        results = reporter._parse_output(output)
        assert results == {}

    def test_parse_relative_path_resolved(self, tmp_path: Path) -> None:
        reporter = TscCLIReporter(tmp_path)
        output = "src/app.ts(1,1): error TS2304: Cannot find name 'foo'.\n"
        results = reporter._parse_output(output)
        assert len(results) == 1
        key = list(results.keys())[0]
        assert key.is_absolute()
        assert key == tmp_path / "src/app.ts"

    def test_parse_multiple_files(self, tmp_path: Path) -> None:
        reporter = TscCLIReporter(tmp_path)
        output = (
            f"{tmp_path}/a.ts(1,1): error TS2304: issue in a\n"
            f"{tmp_path}/b.ts(2,3): error TS2322: issue in b\n"
            f"{tmp_path}/a.ts(5,1): warning TS6133: another issue in a\n"
        )
        results = reporter._parse_output(output)
        assert len(results) == 2
        assert len(results[tmp_path / "a.ts"]) == 2
        assert len(results[tmp_path / "b.ts"]) == 1

    def test_parse_line_1_col_1_becomes_0_0(self, tmp_path: Path) -> None:
        """Verify minimum 1-indexed values map to 0-indexed 0."""
        reporter = TscCLIReporter(tmp_path)
        output = f"{tmp_path}/app.ts(1,1): error TS2304: Cannot find name 'x'.\n"
        results = reporter._parse_output(output)
        diags = list(results.values())[0]
        assert diags[0].range.start.line == 0
        assert diags[0].range.start.character == 0

    def test_parse_start_equals_end(self, tmp_path: Path) -> None:
        """tsc gives a point location; start and end should be the same."""
        reporter = TscCLIReporter(tmp_path)
        output = f"{tmp_path}/app.ts(3,7): error TS2322: msg\n"
        results = reporter._parse_output(output)
        diags = list(results.values())[0]
        d = diags[0]
        assert d.range.start.line == d.range.end.line
        assert d.range.start.character == d.range.end.character

    def test_parse_message_with_colons(self, tmp_path: Path) -> None:
        """Messages containing colons should be captured fully."""
        reporter = TscCLIReporter(tmp_path)
        msg = "Type 'string' is not assignable to type 'number': expected number, got string"
        output = f"{tmp_path}/app.ts(4,2): error TS2322: {msg}\n"
        results = reporter._parse_output(output)
        diags = list(results.values())[0]
        assert msg in diags[0].message

    def test_parse_tsx_file(self, tmp_path: Path) -> None:
        reporter = TscCLIReporter(tmp_path)
        output = f"{tmp_path}/Component.tsx(5,3): error TS2322: msg\n"
        results = reporter._parse_output(output)
        assert len(results) == 1
        key = list(results.keys())[0]
        assert key.name == "Component.tsx"

    def test_parse_summary_lines_skipped(self, tmp_path: Path) -> None:
        """Summary lines like 'Found N errors...' must be skipped."""
        reporter = TscCLIReporter(tmp_path)
        output = (
            f"{tmp_path}/app.ts(1,1): error TS2304: Cannot find name 'x'.\n"
            "\n"
            "Found 1 error in 1 file.\n"
        )
        results = reporter._parse_output(output)
        assert len(results) == 1
        diags = list(results.values())[0]
        assert len(diags) == 1

    def test_parse_mixed_severities(self, tmp_path: Path) -> None:
        reporter = TscCLIReporter(tmp_path)
        output = (
            f"{tmp_path}/app.ts(1,1): error TS2304: an error\n"
            f"{tmp_path}/app.ts(2,1): warning TS6133: a warning\n"
        )
        results = reporter._parse_output(output)
        diags = results[tmp_path / "app.ts"]
        severities = {d.severity for d in diags}
        assert DiagnosticSeverity.ERROR in severities
        assert DiagnosticSeverity.WARNING in severities

    def test_parse_absolute_path_preserved(self, tmp_path: Path) -> None:
        reporter = TscCLIReporter(tmp_path)
        abs_path = str(tmp_path / "deep" / "module.ts")
        output = f"{abs_path}(7,4): error TS2551: msg\n"
        results = reporter._parse_output(output)
        key = list(results.keys())[0]
        assert str(key) == abs_path


@pytest.mark.skipif(not TSC_AVAILABLE, reason="tsc not installed")
class TestTscCLIIntegration:
    async def test_not_found_tsc(self, tmp_path: Path) -> None:
        reporter = TscCLIReporter(tmp_path, tsc_path="/nonexistent/tsc")
        diags = await reporter.get_diagnostics(tmp_path / "app.ts")
        assert diags == []

    async def test_workspace_diagnostics_returns_dict(self, workspace: Path) -> None:
        reporter = TscCLIReporter(workspace)
        results = await reporter.get_all_diagnostics()
        assert isinstance(results, dict)

    async def test_file_with_errors(self, workspace: Path) -> None:
        reporter = TscCLIReporter(workspace)
        diags = await reporter.get_diagnostics(workspace / "error.ts")
        assert len(diags) > 0
        assert all(d.source == "tsc" for d in diags)
        assert all(d.severity == DiagnosticSeverity.ERROR for d in diags)

    async def test_clean_file(self, workspace: Path) -> None:
        reporter = TscCLIReporter(workspace)
        diags = await reporter.get_diagnostics(workspace / "clean.ts")
        errors = [d for d in diags if d.severity == DiagnosticSeverity.ERROR]
        assert errors == []

    async def test_get_diagnostics_nonexistent_file(self, workspace: Path) -> None:
        reporter = TscCLIReporter(workspace)
        diags = await reporter.get_diagnostics(workspace / "nonexistent.ts")
        assert isinstance(diags, list)

    async def test_file_with_errors_no_tsconfig(self, workspace_no_tsconfig: Path) -> None:
        """Single-file diagnostics must work even without tsconfig.json."""
        reporter = TscCLIReporter(workspace_no_tsconfig)
        diags = await reporter.get_diagnostics(workspace_no_tsconfig / "error.ts")
        assert len(diags) > 0
        assert all(d.source == "tsc" for d in diags)

    async def test_clean_file_no_tsconfig(self, workspace_no_tsconfig: Path) -> None:
        """Clean file should have no errors even without tsconfig.json."""
        reporter = TscCLIReporter(workspace_no_tsconfig)
        diags = await reporter.get_diagnostics(workspace_no_tsconfig / "clean.ts")
        errors = [d for d in diags if d.severity == DiagnosticSeverity.ERROR]
        assert errors == []
