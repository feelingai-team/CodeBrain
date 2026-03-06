"""FastMCP server definition exposing CodeBrain tools as MCP tools."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.server.context import Context

from codebrain.core.formatting import format_rename_result
from codebrain.core.workspace import Workspace, WorkspaceManager
from codebrain.mcp import consolidated as _c

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan — manages the workspace manager lifecycle
# ---------------------------------------------------------------------------
@asynccontextmanager
async def _lifespan(server: FastMCP) -> AsyncIterator[dict]:
    initial_root = Path(server.settings.get("workspace_root", ".")).resolve()
    languages = server.settings.get("languages")

    manager = WorkspaceManager()
    manager.set_default_languages(languages)

    # Start the initial workspace
    await manager.get_workspace_for_file(initial_root)

    try:
        yield {"manager": manager}
    finally:
        await manager.stop_all()


# ---------------------------------------------------------------------------
# Server factory
# ---------------------------------------------------------------------------
def create_server(
    workspace_root: str = ".",
    languages: list[str] | None = None,
) -> FastMCP:
    """Create and configure the MCP server."""

    mcp = FastMCP(
        "CodeBrain",
        lifespan=_lifespan,
        settings={
            "workspace_root": workspace_root,
            "languages": languages,
        },
    )

    # ------------------------------------------------------------------
    # Helper to pull shared state from lifespan context
    # ------------------------------------------------------------------
    def _manager(ctx: Context) -> WorkspaceManager:
        return ctx.lifespan_context["manager"]

    async def _get_ws(ctx: Context, file_path: str | Path | None = None) -> Workspace:
        manager = _manager(ctx)
        if file_path:
            ws = await manager.get_workspace_for_file(Path(file_path))
            if ws:
                return ws

        # Fallback to first workspace if any, or create one for current dir
        if manager.workspaces:
            return manager.workspaces[0]

        ws = manager.add_workspace(Path(".").resolve())
        await ws.start()
        return ws

    # ==================================================================
    # Workspace management (kept separate — admin utility)
    # ==================================================================
    @mcp.tool
    async def add_workspace(root_path: str, ctx: Context) -> str:
        """Manually add a new workspace root."""
        manager = _manager(ctx)
        ws = manager.add_workspace(Path(root_path))
        await ws.start()
        return f"Workspace added: {ws.info.root_path} ({ws.info.name})"

    @mcp.tool
    async def list_workspaces(ctx: Context) -> str:
        """List all active workspaces."""
        manager = _manager(ctx)
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
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str:
        """Check code for errors.

        Use file_path for rich per-error context, or directory for a bulk scan.
        """
        ws = await _get_ws(ctx, file_path or directory)
        return await _c.validate(ws, file_path, directory, extensions, max_files)

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
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str:
        """Explore a symbol: definition, type info, references, call hierarchy.

        Use (line, character) for position-based lookup, or symbol_query for name matching.
        """
        ws = await _get_ws(ctx, file_path)
        return await _c.explore_symbol(
            ws, file_path, line, character, symbol_query,
            include_references, include_callers, include_callees,
        )

    # ==================================================================
    # Consolidated tool: outline
    # ==================================================================
    @mcp.tool
    async def outline(
        file_path: str | None = None,
        max_chars: int = 4096,
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str:
        """Get a symbol outline for a file, or a ranked repository map of the whole workspace."""
        ws = await _get_ws(ctx, file_path)
        return await _c.outline(ws, file_path, max_chars)

    # ==================================================================
    # Consolidated tool: check_impact
    # ==================================================================
    @mcp.tool
    async def check_impact(
        file_path: str,
        line: int,
        character: int,
        check_signature: bool = True,
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str:
        """Analyze what breaks if a symbol changes: usages, broken diagnostics, suggested fixes."""
        ws = await _get_ws(ctx, file_path)
        return await _c.check_impact(ws, file_path, line, character, check_signature)

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
        max_results: int = 100,
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str:
        """Search for symbols by name, or structural patterns via tree-sitter.

        Set pattern_mode=True for tree-sitter queries (requires language).
        """
        first_path = file_paths[0] if file_paths else None
        ws = await _get_ws(ctx, first_path)
        return await _c.search(ws, query, language, kind, file_paths, pattern_mode, max_results)

    # ==================================================================
    # Consolidated tool: debug_trace
    # ==================================================================
    @mcp.tool
    async def debug_trace(stack_trace: str, ctx: Context) -> str:
        """Parse a stack trace and enrich each frame with LSP context."""
        ws = await _get_ws(ctx)
        return await _c.debug_trace(ws, stack_trace)

    # ==================================================================
    # Utility: rename_symbol (kept separate — mutating operation)
    # ==================================================================
    @mcp.tool
    async def rename_symbol(
        file_path: str, line: int, character: int, new_name: str, ctx: Context
    ) -> str:
        """Rename a symbol across the workspace."""
        from codebrain.tools.navigation import rename_symbol as _rename

        ws = await _get_ws(ctx, file_path)
        result = await _rename(
            ws.reporter, Path(file_path), line, character, new_name
        )
        return format_rename_result(result)

    return mcp
