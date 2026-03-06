"""MCP tool usage tracing — records call frequency, timing, and result sizes."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_LOG_DIR = Path.home() / ".codebrain" / "traces"


@dataclass
class ToolTrace:
    """A single tool invocation record."""

    tool: str
    timestamp: float
    duration_ms: float
    args: dict
    result_chars: int
    error: str | None = None


@dataclass
class TraceStore:
    """Accumulates tool traces and periodically flushes to disk."""

    log_dir: Path = field(default_factory=lambda: _DEFAULT_LOG_DIR)
    traces: list[ToolTrace] = field(default_factory=list)

    def record(self, trace: ToolTrace) -> None:
        """Record a tool trace and flush immediately."""
        self.traces.append(trace)
        logger.info(
            "tool=%s duration=%.0fms result_chars=%d%s",
            trace.tool,
            trace.duration_ms,
            trace.result_chars,
            f" error={trace.error}" if trace.error else "",
        )
        self.flush()

    def flush(self) -> None:
        """Write buffered traces to a JSONL file."""
        if not self.traces:
            return
        self.log_dir.mkdir(parents=True, exist_ok=True)
        # One file per session, named by first trace timestamp
        session_ts = int(self.traces[0].timestamp)
        log_file = self.log_dir / f"trace-{session_ts}.jsonl"
        with open(log_file, "a") as f:
            for t in self.traces:
                f.write(json.dumps(asdict(t)) + "\n")
        self.traces.clear()

    def summary(self) -> dict[str, dict]:
        """Return per-tool summary stats from all trace files."""
        stats: dict[str, dict] = {}
        if not self.log_dir.exists():
            return stats
        for log_file in sorted(self.log_dir.glob("trace-*.jsonl")):
            for line in log_file.read_text().splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                tool = row["tool"]
                if tool not in stats:
                    stats[tool] = {
                        "calls": 0,
                        "total_ms": 0.0,
                        "errors": 0,
                        "avg_result_chars": 0.0,
                    }
                s = stats[tool]
                s["calls"] += 1
                s["total_ms"] += row["duration_ms"]
                if row.get("error"):
                    s["errors"] += 1
                s["avg_result_chars"] = (
                    (s["avg_result_chars"] * (s["calls"] - 1) + row["result_chars"])
                    / s["calls"]
                )
        return stats


# Global store — created once, shared across server lifetime
_store: TraceStore | None = None


def get_store() -> TraceStore:
    """Get or create the global trace store."""
    global _store
    if _store is None:
        _store = TraceStore()
    return _store
