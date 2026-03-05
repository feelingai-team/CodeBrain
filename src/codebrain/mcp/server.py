"""FastMCP server definition exposing CodeBrain tools as MCP tools."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.server.context import Context

from codebrain.core.formatting import (
    format_call_hierarchy,
    format_diagnostic_context,
    format_diagnostics,
    format_document_symbols,
    format_rename_result,
    format_symbol_locations,
)
from codebrain.core.models import Diagnostic, DiagnosticSeverity, Position, Range
from codebrain.lsp.servers.multi import MultiLanguageReporter
from codebrain.lsp.servers.pyright import PyrightReporter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Language-server registry: maps language name → reporter factory
# ---------------------------------------------------------------------------
_LANGUAGE_FACTORIES: dict[str, type] = {
    "python": PyrightReporter,
}

# Lazy-import optional reporters so missing deps don't break startup.
try:
    from codebrain.lsp.servers.clangd import ClangdReporter

    _LANGUAGE_FACTORIES["cpp"] = ClangdReporter
except ImportError:
    pass

try:
    from codebrain.lsp.servers.typescript import TypeScriptReporter

    _LANGUAGE_FACTORIES["typescript"] = TypeScriptReporter
except ImportError:
    pass


def _build_reporter(
    workspace_root: Path,
    languages: list[str] | None,
) -> MultiLanguageReporter:
    """Build a MultiLanguageReporter for the requested languages."""
    langs = languages or list(_LANGUAGE_FACTORIES.keys())
    reporters = []
    for lang in langs:
        factory = _LANGUAGE_FACTORIES.get(lang)
        if factory is None:
            logger.warning("No reporter factory for language: %s", lang)
            continue
        reporters.append(factory(workspace_root))
    return MultiLanguageReporter(workspace_root, reporters)


# ---------------------------------------------------------------------------
# Lifespan — manages the reporter lifecycle
# ---------------------------------------------------------------------------
@asynccontextmanager
async def _lifespan(server: FastMCP) -> AsyncIterator[dict]:
    workspace = Path(server.settings.get("workspace_root", ".")).resolve()
    languages = server.settings.get("languages")
    reporter = _build_reporter(workspace, languages)
    await reporter.start()

    # Build incremental symbol index in background
    from codebrain.search.index import SymbolIndex

    index = SymbolIndex(workspace)
    await index.build()

    # Start file watcher if watchfiles is available
    watcher = None
    try:
        from codebrain.search.index import FileWatcher

        watcher = FileWatcher(index, workspace)
        await watcher.start()
    except ImportError:
        pass

    try:
        yield {"reporter": reporter, "workspace": workspace, "index": index}
    finally:
        if watcher is not None:
            await watcher.stop()
        await reporter.stop()


# ---------------------------------------------------------------------------
# Server factory
# ---------------------------------------------------------------------------
def create_server(
    workspace_root: str = ".",
    languages: list[str] | None = None,
) -> FastMCP:
    """Create and configure the MCP server. Requires fastmcp optional dependency."""

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
    def _reporter(ctx: Context) -> MultiLanguageReporter:
        return ctx.lifespan_context["reporter"]

    def _workspace(ctx: Context) -> Path:
        return ctx.lifespan_context["workspace"]

    def _index(ctx: Context) -> object:
        return ctx.lifespan_context["index"]

    # ==================================================================
    # Tools — validation
    # ==================================================================
    @mcp.tool
    async def validate_file(file_path: str, ctx: Context) -> str:
        """Run LSP diagnostics on a single file."""
        from codebrain.tools.validation import validate_file as _validate

        diags = await _validate(_reporter(ctx), Path(file_path))
        return format_diagnostics(diags)

    @mcp.tool
    async def validate_workspace(
        directory: str | None = None,
        extensions: list[str] | None = None,
        max_files: int = 100,
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str:
        """Run LSP diagnostics on all files in a directory."""
        from codebrain.tools.validation import validate_workspace as _validate_ws

        target = Path(directory) if directory else _workspace(ctx)
        ext_set = set(extensions) if extensions else None
        results = await _validate_ws(_reporter(ctx), target, ext_set, max_files)
        all_diags: list[Diagnostic] = []
        for diags in results.values():
            all_diags.extend(diags)
        return format_diagnostics(all_diags)

    # ==================================================================
    # Tools — navigation
    # ==================================================================
    @mcp.tool
    async def goto_definition(
        file_path: str, line: int, character: int, ctx: Context
    ) -> str:
        """Find where a symbol is defined."""
        from codebrain.tools.navigation import goto_definition as _goto

        loc = await _goto(_reporter(ctx), Path(file_path), line, character)
        if loc is None:
            return "No definition found."
        return format_symbol_locations([loc])

    @mcp.tool
    async def find_references(
        file_path: str, line: int, character: int, ctx: Context
    ) -> str:
        """Find all references to a symbol."""
        from codebrain.tools.navigation import find_references as _refs

        locs = await _refs(_reporter(ctx), Path(file_path), line, character)
        return format_symbol_locations(locs)

    @mcp.tool
    async def get_hover(file_path: str, line: int, character: int, ctx: Context) -> str:
        """Get type/doc info at a position."""
        from codebrain.tools.navigation import get_hover as _hover

        info = await _hover(_reporter(ctx), Path(file_path), line, character)
        return info or "No hover info."

    @mcp.tool
    async def get_code_actions(
        file_path: str,
        start_line: int,
        start_character: int,
        end_line: int,
        end_character: int,
        severity: int,
        message: str,
        source: str | None = None,
        code: str | None = None,
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str:
        """Get suggested fixes for a diagnostic."""
        from codebrain.tools.navigation import get_code_actions as _actions

        diag = Diagnostic(
            file_path=file_path,
            range=Range(
                start=Position(line=start_line, character=start_character),
                end=Position(line=end_line, character=end_character),
            ),
            severity=DiagnosticSeverity(severity),
            message=message,
            source=source,
            code=code,
        )
        actions = await _actions(_reporter(ctx), diag)
        if not actions:
            return "No code actions available."
        lines = ["**Suggested fixes**:"]
        for a in actions:
            preferred = " (preferred)" if a.is_preferred else ""
            lines.append(f"- {a.title}{preferred}")
        return "\n".join(lines)

    @mcp.tool
    async def document_symbols(file_path: str, ctx: Context) -> str:
        """Get hierarchical symbol outline for a file."""
        from codebrain.tools.navigation import document_symbols as _symbols

        syms = await _symbols(_reporter(ctx), Path(file_path))
        return format_document_symbols(syms)

    @mcp.tool
    async def incoming_calls(
        file_path: str, line: int, character: int, ctx: Context
    ) -> str:
        """Find all callers of a function/method."""
        from codebrain.tools.navigation import incoming_calls as _incoming

        calls = await _incoming(_reporter(ctx), Path(file_path), line, character)
        return format_call_hierarchy(calls, "incoming")

    @mcp.tool
    async def outgoing_calls(
        file_path: str, line: int, character: int, ctx: Context
    ) -> str:
        """Find all functions called by a function/method."""
        from codebrain.tools.navigation import outgoing_calls as _outgoing

        calls = await _outgoing(_reporter(ctx), Path(file_path), line, character)
        return format_call_hierarchy(calls, "outgoing")

    @mcp.tool
    async def rename_symbol(
        file_path: str, line: int, character: int, new_name: str, ctx: Context
    ) -> str:
        """Rename a symbol across the workspace."""
        from codebrain.tools.navigation import rename_symbol as _rename

        result = await _rename(
            _reporter(ctx), Path(file_path), line, character, new_name
        )
        return format_rename_result(result)

    # ==================================================================
    # Tools — search
    # ==================================================================
    @mcp.tool
    async def search_pattern(
        pattern: str,
        language: str,
        file_paths: list[str] | None = None,
        max_results: int = 100,
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str:
        """Search for structural code patterns using tree-sitter queries."""
        from codebrain.tools.search import search_pattern as _search

        paths = [Path(p) for p in file_paths] if file_paths else None
        matches = await _search(_workspace(ctx), pattern, language, paths, max_results)
        if not matches:
            return "No matches found."
        lines: list[str] = []
        for m in matches:
            lines.append(f"- `{m.file_path}:{m.start_line + 1}`: ```{m.text[:120]}```")
        return "\n".join(lines)

    @mcp.tool
    async def search_symbol(
        query: str,
        kind: str | None = None,
        language: str | None = None,
        max_results: int = 100,
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str:
        """Find symbols by name/kind across workspace."""
        from codebrain.tools.search import search_symbol as _search

        symbols = await _search(_workspace(ctx), query, kind, language, max_results)
        if not symbols:
            return "No symbols found."
        lines: list[str] = []
        for s in symbols:
            sig = f" — `{s.signature}`" if s.signature else ""
            lines.append(f"- **{s.name}** ({s.kind}) at `{s.file_path}:{s.line + 1}`{sig}")
        return "\n".join(lines)

    @mcp.tool
    async def get_repomap(
        max_chars: int = 4096,
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str:
        """Generate a concise repository map ranked by symbol importance (PageRank).

        Uses the incremental index for instant results when available.
        """
        from codebrain.search.index import SymbolIndex

        index = _index(ctx)
        if isinstance(index, SymbolIndex) and index.is_built:
            return index.generate_repomap(max_chars)

        from codebrain.search.repomap import generate_repomap as _repomap

        return await _repomap(_workspace(ctx), max_chars)

    # ==================================================================
    # Skills
    # ==================================================================
    @mcp.tool
    async def contextual_diagnostics(file_path: str, ctx: Context) -> str:
        """Validate a file and gather full fix context for each diagnostic."""
        from codebrain.skills.contextual_diagnostics import (
            contextual_diagnostics as _ctx_diag,
        )

        contexts = await _ctx_diag(_reporter(ctx), Path(file_path))
        if not contexts:
            return "No diagnostics found."
        return "\n\n---\n\n".join(format_diagnostic_context(c) for c in contexts)

    @mcp.tool
    async def impact_analysis(
        file_path: str, line: int, character: int, ctx: Context
    ) -> str:
        """For a changed symbol, find all usages and check for breakage."""
        from codebrain.skills.impact_analysis import impact_analysis as _impact

        reporter = _reporter(ctx)
        # impact_analysis requires an LSPReporter — get the one for this file
        lsp_r = reporter.get_reporter_for_file(Path(file_path))
        if lsp_r is None:
            return f"No language server for {file_path}"
        impact, diags = await _impact(lsp_r, Path(file_path), line, character)
        parts: list[str] = [
            f"**Symbol**: {impact.symbol_name}",
            f"**Usages**: {impact.total_usages} across {len(impact.affected_files)} files",
        ]
        if diags:
            parts.append("\n**Broken diagnostics**:")
            parts.append(format_diagnostics(diags))
        return "\n".join(parts)

    @mcp.tool
    async def signature_check(
        file_path: str, line: int, character: int, ctx: Context
    ) -> str:
        """Detect signature changes and their downstream impact."""
        from codebrain.skills.signature_check import signature_check as _sig_check

        reporter = _reporter(ctx)
        lsp_r = reporter.get_reporter_for_file(Path(file_path))
        if lsp_r is None:
            return f"No language server for {file_path}"
        result = await _sig_check(lsp_r, Path(file_path), line, character)
        parts: list[str] = [
            f"**Symbol**: {result.impact.symbol_name}",
            f"**Usages**: {result.impact.total_usages}",
        ]
        if result.hover_info:
            parts.append(f"\n**Current signature**:\n```\n{result.hover_info}\n```")
        if result.broken_diagnostics:
            parts.append("\n**Broken diagnostics**:")
            parts.append(format_diagnostics(result.broken_diagnostics))
        return "\n".join(parts)

    @mcp.tool
    async def look_then_jump(
        file_path: str, symbol_query: str, ctx: Context
    ) -> str:
        """Outline a file, find matching symbols, and jump to their definitions."""
        from codebrain.skills.look_then_jump import look_then_jump as _ltj

        reporter = _reporter(ctx)
        lsp_r = reporter.get_reporter_for_file(Path(file_path))
        if lsp_r is None:
            return f"No language server for {file_path}"
        result = await _ltj(lsp_r, Path(file_path), symbol_query)
        if not result.matches:
            return f"No symbols matching '{symbol_query}' in {file_path}"
        parts: list[str] = [f"**Matches for** `{symbol_query}` in `{file_path}`:"]
        for m in result.matches:
            loc = ""
            if m.definition:
                loc = f" → defined at `{m.definition.file_path}:{m.definition.range.start}`"
            hover = f"\n  ```\n  {m.hover_info}\n  ```" if m.hover_info else ""
            parts.append(f"- **{m.name}** ({m.kind}){loc}{hover}")
        return "\n".join(parts)

    @mcp.tool
    async def analyze_stack_trace(
        stack_trace: str, ctx: Context
    ) -> str:
        """Parse a stack trace and enrich each frame with LSP context."""
        from codebrain.skills.stack_trace import analyze_stack_trace as _analyze

        reporter = _reporter(ctx)
        workspace = _workspace(ctx)
        # Use first available LSP reporter for enrichment
        lsp_r = next(
            (reporter.get_reporter_for_file(Path(f"dummy{ext}"))
             for ext in reporter.supported_extensions
             if reporter.get_reporter_for_file(Path(f"dummy{ext}")) is not None),
            None,
        )
        if lsp_r is None:
            return "No language server available for stack trace analysis."
        result = await _analyze(lsp_r, stack_trace, workspace)
        if not result.frames:
            return "Could not parse any frames from the stack trace."
        parts: list[str] = []
        for i, ef in enumerate(result.frames):
            marker = " **← likely root cause**" if i == result.root_cause_index else ""
            func = ef.frame.function_name or "<unknown>"
            line = f"`{ef.frame.file_path}:{ef.frame.line + 1}` in `{func}`{marker}"
            parts.append(f"- {line}")
            if ef.hover_info:
                parts.append(f"  Type: `{ef.hover_info[:200]}`")
            if ef.definition:
                parts.append(
                    f"  Defined at: `{ef.definition.file_path}:{ef.definition.range.start}`"
                )
        return "\n".join(parts)

    return mcp
