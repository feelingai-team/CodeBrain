"""Skill: Stack Trace Analysis — parse stack traces and enrich frames with LSP context."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from codebrain.core.models import SymbolLocation
from codebrain.lsp.servers.base import LSPReporter


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class StackFrame:
    """A single frame parsed from a stack trace."""

    file_path: str
    line: int  # 0-indexed
    function_name: str | None = None
    column: int | None = None


@dataclass
class EnrichedFrame:
    """A stack frame enriched with LSP context."""

    frame: StackFrame
    hover_info: str | None = None
    definition: SymbolLocation | None = None
    references_count: int = 0


@dataclass
class StackTraceAnalysis:
    """Full analysis of a stack trace."""

    raw_trace: str
    frames: list[EnrichedFrame] = field(default_factory=list)
    root_cause_index: int | None = None


# ---------------------------------------------------------------------------
# Stack trace parsers
# ---------------------------------------------------------------------------

# Python:  File "path/to/file.py", line 42, in func_name
_PYTHON_FRAME = re.compile(
    r'File "(?P<file>[^"]+)", line (?P<line>\d+)(?:, in (?P<func>\S+))?'
)

# JavaScript/TypeScript:  at funcName (file.js:42:10)  OR  at file.js:42:10
_JS_FRAME = re.compile(
    r"at (?:(?P<func>[^\s(]+) )?\(?(?P<file>[^:()]+):(?P<line>\d+)(?::(?P<col>\d+))?\)?"
)

# C/C++ (GDB-style):  #0 0x... in func_name at file.cpp:42
# Also handles:  #0 0x... func_name (args) at file.cpp:42  (no "in" keyword)
_C_FRAME = re.compile(
    r"#\d+\s+(?:0x[0-9a-fA-F]+\s+(?:in\s+)?)?(?P<func>[A-Za-z_]\w*)\s*\([^)]*\)\s+at\s+(?P<file>[^:]+):(?P<line>\d+)"
)

# Go:  path/to/file.go:42 +0x1a  OR  goroutine ... path/to/file.go:42
_GO_FRAME = re.compile(r"(?P<file>[^\s:]+\.go):(?P<line>\d+)")

# Rust:  at /path/to/file.rs:42:10
_RUST_FRAME = re.compile(
    r"at (?P<file>[^:]+\.rs):(?P<line>\d+)(?::(?P<col>\d+))?"
)


def parse_stack_trace(trace: str) -> list[StackFrame]:
    """Parse a stack trace string into structured frames.

    Supports Python, JavaScript/TypeScript, C/C++ (GDB), Go, and Rust formats.
    """
    frames: list[StackFrame] = []
    seen: set[tuple[str, int]] = set()

    # Order matters: more specific patterns first (C/GDB before JS, since
    # JS "at file:line" would also match GDB's "at file.cpp:42").
    patterns: list[tuple[re.Pattern[str], bool]] = [
        (_PYTHON_FRAME, True),
        (_C_FRAME, True),
        (_JS_FRAME, True),
        (_RUST_FRAME, False),
        (_GO_FRAME, False),
    ]

    for line in trace.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        for pattern, has_func in patterns:
            m = pattern.search(stripped)
            if m:
                file_path = m.group("file")
                line_no = int(m.group("line")) - 1  # convert to 0-indexed
                func = m.group("func") if has_func else None

                key = (file_path, line_no)
                if key not in seen:
                    seen.add(key)
                    col_str = m.groupdict().get("col")
                    frames.append(
                        StackFrame(
                            file_path=file_path,
                            line=line_no,
                            function_name=func,
                            column=int(col_str) - 1 if col_str else None,
                        )
                    )
                break

    return frames


# ---------------------------------------------------------------------------
# LSP enrichment
# ---------------------------------------------------------------------------
async def _enrich_frame(
    reporter: LSPReporter,
    frame: StackFrame,
    workspace_root: Path,
) -> EnrichedFrame:
    """Enrich a single stack frame with LSP context."""
    from codebrain.tools.navigation import find_references, get_hover, goto_definition

    # Resolve file path
    fp = Path(frame.file_path)
    if not fp.is_absolute():
        fp = workspace_root / fp
    if not fp.exists():
        return EnrichedFrame(frame=frame)

    char = frame.column or 0

    hover = await get_hover(reporter, fp, frame.line, char)
    defn = await goto_definition(reporter, fp, frame.line, char)
    refs = await find_references(reporter, fp, frame.line, char)

    return EnrichedFrame(
        frame=frame,
        hover_info=hover,
        definition=defn,
        references_count=len(refs),
    )


async def analyze_stack_trace(
    reporter: LSPReporter,
    stack_trace: str,
    workspace_root: Path,
) -> StackTraceAnalysis:
    """Parse a stack trace and enrich each frame with LSP context.

    The root_cause_index points to the deepest frame that is within
    the workspace (i.e. not in third-party/stdlib code).
    """
    parsed = parse_stack_trace(stack_trace)
    enriched: list[EnrichedFrame] = []
    root_cause_index: int | None = None

    for i, frame in enumerate(parsed):
        ef = await _enrich_frame(reporter, frame, workspace_root)
        enriched.append(ef)

        # Track deepest in-workspace frame as likely root cause
        fp = Path(frame.file_path)
        if not fp.is_absolute():
            fp = workspace_root / fp
        try:
            fp.relative_to(workspace_root)
            root_cause_index = i
        except ValueError:
            pass

    return StackTraceAnalysis(
        raw_trace=stack_trace,
        frames=enriched,
        root_cause_index=root_cause_index,
    )
