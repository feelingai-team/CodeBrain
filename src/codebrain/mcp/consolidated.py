"""Consolidated MCP tools — 6 intent-oriented tools wrapping atomic tools and skills."""

from __future__ import annotations

from pathlib import Path

from codebrain.core.formatting import (
    format_call_hierarchy,
    format_diagnostic_context,
    format_diagnostics,
    format_document_symbols,
    format_symbol_locations,
)
from codebrain.core.models import Diagnostic
from codebrain.core.workspace import Workspace


# ---------------------------------------------------------------------------
# 1. validate — "Check my code for errors"
# ---------------------------------------------------------------------------
async def validate(
    ws: Workspace,
    file_path: str | None = None,
    directory: str | None = None,
    extensions: list[str] | None = None,
    max_files: int = 100,
) -> str:
    """Run LSP diagnostics on a file, directory, or entire workspace.

    - file_path → rich contextual diagnostics per error (definition, hover, fixes)
    - directory → bulk scan with plain diagnostics
    - neither → scan the workspace root
    """
    if file_path:
        from codebrain.skills.contextual_diagnostics import (
            contextual_diagnostics as _ctx_diag,
        )

        contexts = await _ctx_diag(ws.reporter, Path(file_path))
        if not contexts:
            return "No diagnostics found."
        return "\n\n---\n\n".join(format_diagnostic_context(c) for c in contexts)

    from codebrain.tools.validation import validate_workspace as _validate_ws

    target = Path(directory) if directory else Path(ws.info.root_path)
    ext_set = set(extensions) if extensions else None
    results = await _validate_ws(ws.reporter, target, ext_set, max_files)
    all_diags: list[Diagnostic] = []
    for diags in results.values():
        all_diags.extend(diags)
    return format_diagnostics(all_diags)


# ---------------------------------------------------------------------------
# 2. explore_symbol — "Tell me about this symbol"
# ---------------------------------------------------------------------------
async def explore_symbol(
    ws: Workspace,
    file_path: str,
    line: int | None = None,
    character: int | None = None,
    symbol_query: str | None = None,
    include_references: bool = False,
    include_callers: bool = False,
    include_callees: bool = False,
) -> str:
    """Explore a symbol: definition, hover, references, call hierarchy.

    - (file_path, line, character) → goto_definition + hover
    - (file_path, symbol_query) → look_then_jump (fuzzy name match)
    - Flags enable additional sections.
    """
    # Look-then-jump mode: find by name without line/character
    if symbol_query and (line is None or character is None):
        from codebrain.skills.look_then_jump import look_then_jump as _ltj

        lsp_r = ws.reporter.get_reporter_for_file(Path(file_path))
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

    # Position-based mode: need line and character
    if line is None or character is None:
        return "Either (line, character) or symbol_query is required."

    from codebrain.tools.navigation import (
        find_references as _refs,
    )
    from codebrain.tools.navigation import (
        get_hover as _hover,
    )
    from codebrain.tools.navigation import (
        goto_definition as _goto,
    )
    from codebrain.tools.navigation import (
        incoming_calls as _incoming,
    )
    from codebrain.tools.navigation import (
        outgoing_calls as _outgoing,
    )

    parts = []

    # Definition
    defn = await _goto(ws.reporter, Path(file_path), line, character)
    if defn:
        parts.append(f"**Definition**: `{defn.file_path}:{defn.range.start}`")
    else:
        parts.append("**Definition**: not found")

    # Hover / type info
    hover = await _hover(ws.reporter, Path(file_path), line, character)
    if hover:
        parts.append(f"\n**Type info**:\n```\n{hover}\n```")

    # References
    if include_references:
        refs = await _refs(ws.reporter, Path(file_path), line, character)
        if refs:
            parts.append(f"\n**References** ({len(refs)}):")
            parts.append(format_symbol_locations(refs))
        else:
            parts.append("\n**References**: none found")

    # Incoming calls
    if include_callers:
        calls = await _incoming(ws.reporter, Path(file_path), line, character)
        parts.append("\n" + format_call_hierarchy(calls, "incoming"))

    # Outgoing calls
    if include_callees:
        calls = await _outgoing(ws.reporter, Path(file_path), line, character)
        parts.append("\n" + format_call_hierarchy(calls, "outgoing"))

    return "\n".join(parts) if parts else "No information found."


# ---------------------------------------------------------------------------
# 3. outline — "What's in this file/repo"
# ---------------------------------------------------------------------------
async def outline(
    ws: Workspace,
    file_path: str | None = None,
    max_chars: int = 4096,
) -> str:
    """Get a symbol outline for a file, or a ranked repository map.

    - file_path → hierarchical document symbols
    - no file_path → workspace-wide repomap ranked by importance
    """
    if file_path:
        from codebrain.tools.navigation import document_symbols as _symbols

        syms = await _symbols(ws.reporter, Path(file_path))
        return format_document_symbols(syms)

    # Workspace-wide repomap
    if ws.index.is_built:
        return ws.index.generate_repomap(max_chars)

    from codebrain.search.repomap import generate_repomap as _repomap

    return await _repomap(Path(ws.info.root_path), max_chars)


# ---------------------------------------------------------------------------
# 4. check_impact — "What breaks if I change this"
# ---------------------------------------------------------------------------
async def check_impact(
    ws: Workspace,
    file_path: str,
    line: int,
    character: int,
    check_signature: bool = True,
) -> str:
    """Analyze the impact of changing a symbol: usages, breakage, fixes.

    - Always runs impact_analysis (find usages + check for broken diagnostics)
    - check_signature=True adds current signature info
    - Appends code action suggestions for any broken diagnostics
    """
    lsp_r = ws.reporter.get_reporter_for_file(Path(file_path))
    if lsp_r is None:
        return f"No language server for {file_path}"

    parts: list[str] = []

    if check_signature:
        from codebrain.skills.signature_check import signature_check as _sig_check

        result = await _sig_check(lsp_r, Path(file_path), line, character)
        parts.append(f"**Symbol**: {result.impact.symbol_name}")
        parts.append(
            f"**Usages**: {result.impact.total_usages} "
            f"across {len(result.impact.affected_files)} files"
        )
        if result.hover_info:
            parts.append(f"\n**Current signature**:\n```\n{result.hover_info}\n```")
        broken_diags = result.broken_diagnostics
    else:
        from codebrain.skills.impact_analysis import impact_analysis as _impact

        impact, broken_diags = await _impact(lsp_r, Path(file_path), line, character)
        parts.append(f"**Symbol**: {impact.symbol_name}")
        parts.append(
            f"**Usages**: {impact.total_usages} "
            f"across {len(impact.affected_files)} files"
        )

    if broken_diags:
        parts.append("\n**Broken diagnostics**:")
        parts.append(format_diagnostics(broken_diags))

        # Gather code actions for broken diagnostics
        from codebrain.tools.navigation import get_code_actions as _actions

        all_actions: list[str] = []
        for diag in broken_diags:
            actions = await _actions(ws.reporter, diag)
            for a in actions:
                preferred = " (preferred)" if a.is_preferred else ""
                all_actions.append(f"- {a.title}{preferred}")
        if all_actions:
            parts.append("\n**Suggested fixes**:")
            parts.extend(all_actions)

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# 5. search — "Find code matching X"
# ---------------------------------------------------------------------------
async def search(
    ws: Workspace,
    query: str,
    language: str | None = None,
    kind: str | None = None,
    file_paths: list[str] | None = None,
    pattern_mode: bool = False,
    max_results: int = 100,
) -> str:
    """Search for symbols by name or structural patterns via tree-sitter.

    - pattern_mode=False (default) → symbol name search
    - pattern_mode=True → tree-sitter query (requires language)
    """
    root = Path(ws.info.root_path)

    if pattern_mode:
        if not language:
            return "pattern_mode=True requires a language parameter."

        from codebrain.tools.search import search_pattern as _search_pat

        paths = [Path(p) for p in file_paths] if file_paths else None
        matches = await _search_pat(root, query, language, paths, max_results)
        if not matches:
            return "No matches found."
        lines: list[str] = []
        for m in matches:
            lines.append(f"- `{m.file_path}:{m.start_line + 1}`: ```{m.text[:120]}```")
        return "\n".join(lines)

    from codebrain.tools.search import search_symbol as _search_sym

    symbols = await _search_sym(root, query, kind, language, max_results)
    if not symbols:
        return "No symbols found."
    lines = []
    for s in symbols:
        sig = f" — `{s.signature}`" if s.signature else ""
        lines.append(f"- **{s.name}** ({s.kind}) at `{s.file_path}:{s.line + 1}`{sig}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 6. debug_trace — "Debug this error"
# ---------------------------------------------------------------------------
async def debug_trace(
    ws: Workspace,
    stack_trace: str,
) -> str:
    """Parse a stack trace and enrich each frame with LSP context."""
    from codebrain.skills.stack_trace import analyze_stack_trace as _analyze

    # Use first available LSP reporter for enrichment
    lsp_r = next(
        (
            ws.reporter.get_reporter_for_file(Path(f"dummy{ext}"))
            for ext in ws.reporter.supported_extensions
            if ws.reporter.get_reporter_for_file(Path(f"dummy{ext}")) is not None
        ),
        None,
    )
    if lsp_r is None:
        return "No language server available for stack trace analysis."
    result = await _analyze(lsp_r, stack_trace, Path(ws.info.root_path))
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
