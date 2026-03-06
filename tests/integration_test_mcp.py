"""Integration test: run CodeBrain consolidated tools against the real codebase."""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from pathlib import Path

# Ensure the package is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

WORKSPACE = Path(__file__).parent.parent

# Enable logging so we can see LSP startup progress
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)


async def main() -> None:
    from codebrain.core.workspace import WorkspaceManager
    from codebrain.mcp import consolidated as tools
    from codebrain.mcp.tracing import ToolTrace, get_store

    store = get_store()

    print("=" * 60)
    print("CodeBrain Integration Test (consolidated tools)")
    print("=" * 60)

    # Set up workspace (same as MCP lifespan does)
    print("\nStarting workspace (this includes LSP + index build)...")
    t_start = time.monotonic()
    manager = WorkspaceManager()
    manager.set_default_languages(["python"])
    ws = await asyncio.wait_for(
        manager.get_workspace_for_file(WORKSPACE.resolve()),
        timeout=120,
    )
    assert ws is not None, "Failed to create workspace"
    dt = (time.monotonic() - t_start) * 1000
    print(f"Workspace ready: {ws.info.name} @ {ws.info.root_path} ({dt:.0f}ms)")

    target_file = str(WORKSPACE / "src/codebrain/mcp/server.py")

    def _record(name: str, t0: float, result: str) -> None:
        store.record(ToolTrace(
            tool=name,
            timestamp=t0,
            duration_ms=(time.monotonic() - t0) * 1000,
            args={},
            result_chars=len(result),
        ))

    # Test 1: outline (repomap — no file_path)
    print("\n--- Test 1: outline (repomap) ---")
    t0 = time.monotonic()
    text = await tools.outline(ws, file_path=None, max_chars=2048)
    dt = (time.monotonic() - t0) * 1000
    _record("outline", t0, text)
    print(f"  Time: {dt:.0f}ms | Chars: {len(text)}")
    print(f"  Preview: {text[:200]}...")
    assert len(text) > 0, "outline returned empty"
    print("  PASS")

    # Test 2: outline (single file)
    print("\n--- Test 2: outline (file: server.py) ---")
    t0 = time.monotonic()
    text = await tools.outline(ws, file_path=target_file, max_chars=4096)
    dt = (time.monotonic() - t0) * 1000
    _record("outline", t0, text)
    print(f"  Time: {dt:.0f}ms | Chars: {len(text)}")
    print(f"  Preview: {text[:200]}...")
    print("  PASS")

    # Test 3: search (symbol search)
    print("\n--- Test 3: search (symbol: 'Workspace') ---")
    t0 = time.monotonic()
    text = await tools.search(ws, query="Workspace")
    dt = (time.monotonic() - t0) * 1000
    _record("search", t0, text)
    print(f"  Time: {dt:.0f}ms | Chars: {len(text)}")
    print(f"  Preview: {text[:300]}...")
    assert "Workspace" in text or "No symbols" in text, "search failed"
    print("  PASS")

    # Test 4: search (pattern mode)
    print("\n--- Test 4: search (pattern: class definitions, python) ---")
    t0 = time.monotonic()
    text = await tools.search(
        ws,
        query="(class_definition name: (identifier) @name)",
        language="python",
        pattern_mode=True,
        max_results=10,
    )
    dt = (time.monotonic() - t0) * 1000
    _record("search", t0, text)
    print(f"  Time: {dt:.0f}ms | Chars: {len(text)}")
    print(f"  Preview: {text[:300]}...")
    print("  PASS")

    # Test 5: validate (single file)
    print("\n--- Test 5: validate (file: server.py) ---")
    t0 = time.monotonic()
    text = await tools.validate(ws, file_path=target_file)
    dt = (time.monotonic() - t0) * 1000
    _record("validate", t0, text)
    print(f"  Time: {dt:.0f}ms | Chars: {len(text)}")
    print(f"  Preview: {text[:300]}...")
    print("  PASS")

    # Test 6: validate (workspace scan)
    print("\n--- Test 6: validate (workspace scan) ---")
    t0 = time.monotonic()
    text = await tools.validate(
        ws, directory=str(WORKSPACE / "src/codebrain/mcp"), max_files=10
    )
    dt = (time.monotonic() - t0) * 1000
    _record("validate", t0, text)
    print(f"  Time: {dt:.0f}ms | Chars: {len(text)}")
    print(f"  Preview: {text[:300]}...")
    print("  PASS")

    # Flush traces and print summary
    store.flush()
    summary = store.summary()
    print("\n" + "=" * 60)
    print("Trace Summary")
    print("=" * 60)
    for tool, stats in sorted(summary.items()):
        print(
            f"  {tool}: {stats['calls']} calls, "
            f"avg {stats['total_ms']/stats['calls']:.0f}ms, "
            f"avg {stats['avg_result_chars']:.0f} chars"
        )

    print(f"\nTrace file: {store.log_dir}")

    # Cleanup
    await manager.stop_all()
    print("\nAll tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
