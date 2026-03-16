"""FastMCP server definition exposing CodeBrain tools as MCP tools."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastmcp import FastMCP

from codebrain.core.formatting import format_rename_result
from codebrain.core.workspace import Workspace, WorkspaceManager
from codebrain.mcp import consolidated as _c
from codebrain.mcp.tracing import ToolTrace, get_store

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Server factory
# ---------------------------------------------------------------------------
def create_server(
    workspace_root: str = ".",
    languages: list[str] | None = None,
) -> FastMCP:
    """Create and configure the MCP server."""

    # Shared state — populated by lifespan, accessed by all tool closures
    manager = WorkspaceManager()
    manager.set_default_languages(languages)

    @asynccontextmanager
    async def _lifespan(_server: FastMCP) -> AsyncIterator[None]:
        # Don't eagerly start language servers — they'll start lazily
        # on the first tool call. This keeps lifespan fast (< 1s) so
        # the MCP connection doesn't time out.
        store = get_store()

        try:
            yield
        finally:
            store.flush()
            await manager.stop_all()

    mcp = FastMCP("CodeBrain", lifespan=_lifespan)

    # ------------------------------------------------------------------
    # Helpers (capture `manager` from closure)
    # ------------------------------------------------------------------
    def _trace(tool_name: str, args: dict, t0: float, result: str) -> None:
        get_store().record(ToolTrace(
            tool=tool_name,
            timestamp=time.time(),
            duration_ms=(time.monotonic() - t0) * 1000,
            args=args,
            result_chars=len(result),
        ))

    def _resolve(file_path: str | None) -> str | None:
        """Resolve a potentially relative file path to an absolute one."""
        if file_path is None:
            return None
        p = Path(file_path)
        if not p.is_absolute():
            p = Path(workspace_root).resolve() / p
        return str(p)

    async def _get_ws(file_path: str | Path | None = None) -> Workspace:
        if file_path:
            p = Path(file_path)
            if not p.is_absolute():
                p = Path(workspace_root).resolve() / p
            ws = await manager.get_workspace_for_file(p)
            if ws:
                return ws

        # Fallback to first workspace if any, or create one for current dir
        if manager.workspaces:
            return manager.workspaces[0]

        ws = manager.add_workspace(Path(workspace_root).resolve())
        await ws.start()
        return ws

    # ==================================================================
    # Workspace management (kept separate — admin utility)
    # ==================================================================
    @mcp.tool
    async def add_workspace(root_path: str) -> str:
        """Manually add a new workspace root."""
        ws = manager.add_workspace(Path(root_path))
        await ws.start()
        return f"Workspace added: {ws.info.root_path} ({ws.info.name})"

    @mcp.tool
    async def list_workspaces() -> str:
        """List all active workspaces."""
        if not manager.workspaces:
            return "No active workspaces."
        lines = ["Active workspaces:"]
        for ws in manager.workspaces:
            lines.append(f"- {ws.info.name}: `{ws.info.root_path}`")
        return "\n".join(lines)

    # ==================================================================
    # Consolidated tool: validate
    # ==================================================================
    @mcp.tool
    async def validate(
        file_path: str | None = None,
        directory: str | None = None,
        extensions: list[str] | None = None,
        max_files: int = 100,
        min_severity: str | None = None,
    ) -> str:
        """Check code for errors.

        Use file_path for rich per-error context, or directory for a bulk scan.
        min_severity filters results: "error", "warning", "information", or "hint" (default: all).
        """
        t0 = time.monotonic()
        file_path = _resolve(file_path)
        directory = _resolve(directory)
        ws = await _get_ws(file_path or directory)
        result = await _c.validate(
            ws, file_path, directory, extensions, max_files, min_severity,
        )
        _trace("validate", {"file_path": file_path, "directory": directory}, t0, result)
        return result

    # ==================================================================
    # Consolidated tool: explore_symbol
    # ==================================================================
    @mcp.tool
    async def explore_symbol(
        file_path: str,
        line: int | None = None,
        character: int | None = None,
        symbol_query: str | None = None,
        include_references: bool = False,
        include_callers: bool = False,
        include_callees: bool = False,
    ) -> str:
        """Explore a symbol: definition, type info, references, call hierarchy.

        Use (line, character) for position-based lookup, or symbol_query for name matching.
        """
        t0 = time.monotonic()
        file_path = _resolve(file_path) or file_path
        ws = await _get_ws(file_path)
        result = await _c.explore_symbol(
            ws, file_path, line, character, symbol_query,
            include_references, include_callers, include_callees,
        )
        _trace(
            "explore_symbol",
            {"file_path": file_path, "line": line, "symbol_query": symbol_query},
            t0, result,
        )
        return result

    # ==================================================================
    # Consolidated tool: outline
    # ==================================================================
    @mcp.tool
    async def outline(
        file_path: str | None = None,
        max_chars: int = 8192,
    ) -> str:
        """Get a symbol outline for a file, or a ranked repository map of the whole workspace."""
        t0 = time.monotonic()
        file_path = _resolve(file_path)
        ws = await _get_ws(file_path)
        result = await _c.outline(ws, file_path, max_chars)
        _trace("outline", {"file_path": file_path}, t0, result)
        return result

    # ==================================================================
    # Consolidated tool: check_impact
    # ==================================================================
    @mcp.tool
    async def check_impact(
        file_path: str,
        line: int,
        character: int,
        check_signature: bool = True,
    ) -> str:
        """Analyze what breaks if a symbol changes: usages, broken diagnostics, suggested fixes."""
        t0 = time.monotonic()
        file_path = _resolve(file_path) or file_path
        ws = await _get_ws(file_path)
        result = await _c.check_impact(ws, file_path, line, character, check_signature)
        _trace("check_impact", {"file_path": file_path, "line": line}, t0, result)
        return result

    # ==================================================================
    # Consolidated tool: search
    # ==================================================================
    @mcp.tool
    async def search(
        query: str,
        language: str | None = None,
        kind: str | None = None,
        file_paths: list[str] | None = None,
        pattern_mode: bool = False,
        scope: str = "definitions",
        max_results: int = 100,
    ) -> str:
        """Search for code by name.

        Default searches symbol definitions (functions, classes, types).
        Use scope="identifiers" to find ALL identifier usages (method calls, variable refs).
        Use scope="all" for both definitions and usages.

        Query modes:
          search(query="HandleMotion")                  # exact/substring match
          search(query="motion handler")                # multi-keyword AND
          search(query="StreamParser|FrameParser")      # pipe OR (best match wins)
          search(query="Motion*")                       # glob pattern

        Use kind to filter definitions (e.g. kind="function", kind="class").
        Set pattern_mode=True for tree-sitter structural queries (requires language).
        """
        t0 = time.monotonic()
        if file_paths:
            file_paths = [_resolve(p) or p for p in file_paths]
        first_path = file_paths[0] if file_paths else None
        ws = await _get_ws(first_path)
        result = await _c.search(
            ws, query, language, kind, file_paths, pattern_mode, scope, max_results,
        )
        _trace("search", {"query": query, "pattern_mode": pattern_mode}, t0, result)
        return result

    # ==================================================================
    # Consolidated tool: debug_trace
    # ==================================================================
    @mcp.tool
    async def debug_trace(stack_trace: str) -> str:
        """Parse a stack trace and enrich each frame with LSP context."""
        t0 = time.monotonic()
        ws = await _get_ws()
        result = await _c.debug_trace(ws, stack_trace)
        _trace("debug_trace", {}, t0, result)
        return result

    # ==================================================================
    # Utility: rename_symbol (kept separate — mutating operation)
    # ==================================================================
    @mcp.tool
    async def rename_symbol(
        file_path: str, line: int, character: int, new_name: str,
    ) -> str:
        """Rename a symbol across the workspace."""
        from codebrain.tools.navigation import rename_symbol as _rename

        file_path = _resolve(file_path) or file_path
        ws = await _get_ws(file_path)
        result = await _rename(
            ws.reporter, Path(file_path), line, character, new_name
        )
        return format_rename_result(result)

    # ==================================================================
    # Tool: check_health
    # ==================================================================
    @mcp.tool
    async def check_health(workspace_path: str | None = None) -> str:
        """Check language server health for all sub-projects.

        Returns status (active/degraded/unavailable) per language per sub-project,
        with remediation hints for any issues.
        """
        import datetime as _dt

        from codebrain.core.models import HealthReport, LanguageHealth, SubProjectHealth
        from codebrain.fallback.hints import get_hints

        ws = await _get_ws(workspace_path)
        root = Path(ws.info.root_path)

        # Trigger scan if not done
        if not manager.registry._sub_projects:
            await manager.registry.scan(root)

        sub_projects = [
            sp for sp in manager.registry._sub_projects
            if sp.root.is_relative_to(root)
        ]
        sp_healths: list[SubProjectHealth] = []

        # Dummy extension map for checking reporter availability
        _lang_ext: dict[str, str] = {
            "python": "x.py", "go": "x.go", "typescript": "x.ts", "cpp": "x.cpp",
        }

        for sp in sub_projects:
            lang_health: dict[str, LanguageHealth] = {}
            for lang in sp.languages:
                from typing import Literal, cast

                ext_file = _lang_ext.get(lang.value, "x")
                reporter = ws.reporter.get_reporter_for_file(Path(ext_file))
                status_val: Literal["active", "degraded", "unavailable"]
                if reporter is None:
                    status_val = "unavailable"
                    hints = get_hints(lang.value, "server_missing")
                    server_name = lang.value
                elif hasattr(reporter, "status"):
                    # FallbackChain exposes .status
                    raw_status = getattr(reporter, "status", "unavailable")
                    status_val = cast(
                        Literal["active", "degraded", "unavailable"],
                        raw_status if raw_status in ("active", "degraded", "unavailable")
                        else "unavailable",
                    )
                    hints = getattr(reporter, "hints", [])
                    server_name = reporter.name
                elif hasattr(reporter, "is_running") and reporter.is_running:
                    status_val = "active"
                    hints = []
                    server_name = reporter.name
                else:
                    status_val = "unavailable"
                    hints = get_hints(lang.value, "server_missing")
                    server_name = reporter.name

                lang_health[lang.value] = LanguageHealth(
                    status=status_val,
                    server=server_name,
                    hints=hints,
                )
            sp_healths.append(SubProjectHealth(root=sp.root, languages=lang_health))

        report = HealthReport(
            workspace_root=root,
            timestamp=_dt.datetime.now(tz=_dt.UTC),
            sub_projects=sp_healths,
        )

        lines = [f"# Health Report: {root.name}", ""]
        for sph in report.sub_projects:
            try:
                rel = sph.root.relative_to(root)
            except ValueError:
                rel = sph.root
            lines.append(f"## {rel}")
            for lang, lh in sph.languages.items():
                icon = {"active": "✅", "degraded": "⚠️", "unavailable": "❌"}.get(
                    lh.status, "?"
                )
                lines.append(f"  {icon} {lang}: {lh.status} ({lh.server})")
                for hint in lh.hints:
                    lines.append(f"    → {hint}")
            lines.append("")

        return "\n".join(lines)

    # ==================================================================
    # Tool: list_subprojects
    # ==================================================================
    @mcp.tool
    async def list_subprojects(workspace_path: str | None = None) -> str:
        """List all detected sub-projects in the workspace with their languages."""
        ws = await _get_ws(workspace_path)
        root = Path(ws.info.root_path)

        # Trigger scan if not done
        if not manager.registry._sub_projects:
            await manager.registry.scan(root)

        sub_projects = [
            sp for sp in manager.registry._sub_projects
            if sp.root.is_relative_to(root)
        ]

        if not sub_projects:
            return "No sub-projects detected."

        lines = [f"Sub-projects in {root.name}:", ""]
        for sp in sorted(sub_projects, key=lambda s: str(s.root)):
            rel = sp.root.relative_to(root) if sp.root != root else Path(".")
            langs = ", ".join(lang.value for lang in sp.languages)
            markers = ", ".join(sp.markers.keys())
            lines.append(f"- **{rel}** [{langs}] (markers: {markers})")
            if sp.parent:
                try:
                    parent_rel = sp.parent.relative_to(root)
                    lines.append(f"  parent: {parent_rel}")
                except ValueError:
                    lines.append(f"  parent: {sp.parent}")
        return "\n".join(lines)

    return mcp
