"""Tests for stack trace parsing (unit tests — no LSP needed)."""

from __future__ import annotations

from codebrain.skills.stack_trace import StackFrame, parse_stack_trace

PYTHON_TRACE = """\
Traceback (most recent call last):
  File "/app/main.py", line 10, in main
    result = process(data)
  File "/app/processor.py", line 42, in process
    return transform(data)
  File "/app/transform.py", line 7, in transform
    raise ValueError("bad input")
ValueError: bad input
"""

JS_TRACE = """\
TypeError: Cannot read property 'name' of undefined
    at processUser (/app/src/users.js:15:23)
    at handleRequest (/app/src/server.js:42:10)
    at /app/src/index.js:8:5
"""

GDB_TRACE = """\
#0  0x00007f9a crash_func (arg=0x0) at /app/src/main.cpp:42
#1  0x00007f9b caller_func () at /app/src/caller.cpp:15
#2  0x00007f9c main () at /app/src/entry.cpp:8
"""

GO_TRACE = """\
goroutine 1 [running]:
main.processRequest(...)
	/app/handler.go:42
main.main()
	/app/main.go:15 +0x1a
"""

RUST_TRACE = """\
   0: std::backtrace_rs::backtrace::trace
             at /rustc/abc123/library/std/src/backtrace.rs:100:18
   1: myapp::handler::process
             at /app/src/handler.rs:42:5
   2: myapp::main
             at /app/src/main.rs:15:10
"""


class TestPythonParsing:
    def test_extracts_frames(self) -> None:
        frames = parse_stack_trace(PYTHON_TRACE)
        assert len(frames) == 3

    def test_frame_details(self) -> None:
        frames = parse_stack_trace(PYTHON_TRACE)
        assert frames[0] == StackFrame(
            file_path="/app/main.py", line=9, function_name="main"
        )
        assert frames[1] == StackFrame(
            file_path="/app/processor.py", line=41, function_name="process"
        )

    def test_zero_indexed_lines(self) -> None:
        frames = parse_stack_trace(PYTHON_TRACE)
        # line 10 in trace → 9 in 0-indexed
        assert frames[0].line == 9


class TestJavaScriptParsing:
    def test_extracts_frames(self) -> None:
        frames = parse_stack_trace(JS_TRACE)
        assert len(frames) == 3

    def test_named_function(self) -> None:
        frames = parse_stack_trace(JS_TRACE)
        assert frames[0].function_name == "processUser"
        assert frames[0].file_path == "/app/src/users.js"
        assert frames[0].line == 14  # 15 - 1

    def test_anonymous_frame(self) -> None:
        frames = parse_stack_trace(JS_TRACE)
        # "at /app/src/index.js:8:5" — no function name
        assert frames[2].function_name is None


class TestCppParsing:
    def test_extracts_frames(self) -> None:
        frames = parse_stack_trace(GDB_TRACE)
        assert len(frames) == 3

    def test_frame_details(self) -> None:
        frames = parse_stack_trace(GDB_TRACE)
        assert frames[0].function_name == "crash_func"
        assert frames[0].file_path == "/app/src/main.cpp"
        assert frames[0].line == 41


class TestGoParsing:
    def test_extracts_frames(self) -> None:
        frames = parse_stack_trace(GO_TRACE)
        assert len(frames) >= 2

    def test_frame_files(self) -> None:
        frames = parse_stack_trace(GO_TRACE)
        paths = [f.file_path for f in frames]
        assert "/app/handler.go" in paths
        assert "/app/main.go" in paths


class TestRustParsing:
    def test_extracts_frames(self) -> None:
        frames = parse_stack_trace(RUST_TRACE)
        assert len(frames) >= 2

    def test_workspace_frames(self) -> None:
        frames = parse_stack_trace(RUST_TRACE)
        paths = [f.file_path for f in frames]
        assert "/app/src/handler.rs" in paths


class TestDeduplication:
    def test_no_duplicates(self) -> None:
        """Same file:line should only appear once even if matched by multiple patterns."""
        trace = 'File "/app/main.py", line 10, in main\nFile "/app/main.py", line 10, in main'
        frames = parse_stack_trace(trace)
        assert len(frames) == 1


class TestEmptyTrace:
    def test_empty_string(self) -> None:
        assert parse_stack_trace("") == []

    def test_no_frames(self) -> None:
        assert parse_stack_trace("just some random text\nwith no frames") == []
