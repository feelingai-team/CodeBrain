"""Consolidated MCP tools — 6 intent-oriented tools wrapping atomic tools and skills."""

from __future__ import annotations

from pathlib import Path

from codebrain.core.formatting import (
    _read_source_line,
    format_call_hierarchy,
    format_diagnostic_context,
    format_diagnostics,
    format_document_symbols,
    format_symbol_locations,
    read_source_span,
)
from codebrain.core.models import Diagnostic
from codebrain.core.workspace import Workspace

# ---------------------------------------------------------------------------
# 1. validate — "Check my code for errors"
# ---------------------------------------------------------------------------
_SEVERITY_NAMES: dict[str, int] = {
    "error": 1,
    "warning": 2,
    "information": 3,
    "info": 3,
    "hint": 4,
}


def _get_health_hints(ws: Workspace, file_path: str | None = None) -> tuple[str, str]:
    """Return (header_warning, footer_note) based on reporter health status.

    header_warning: non-empty when a reporter is unavailable (critical — results may be wrong)
    footer_note: non-empty when a reporter is degraded (informational — results are partial)
    """
    from codebrain.fallback.hints import get_hints

    header = ""
    footer = ""

    # Determine which reporter to check
    if file_path:
        reporter = ws.reporter.get_reporter_for_file(Path(file_path))
    else:
        reporter = None

    # Check all reporters if no specific file
    reporters_to_check = [reporter] if reporter else []
    if not reporters_to_check:
        for ext in (".py", ".go", ".ts", ".cpp"):
            r = ws.reporter.get_reporter_for_file(Path(f"x{ext}"))
            if r is not None:
                reporters_to_check.append(r)

    for r in reporters_to_check:
        if r is None:
            continue
        status = getattr(r, "status", None)
        if status == "unavailable":
            hints = getattr(r, "hints", None) or get_hints(r.name, "server_missing")
            hint_text = " ".join(hints[:1]) if hints else ""
            header = (
                f"⚠️ **{r.name} language server unavailable** — "
                f"diagnostics may be incomplete or missing. {hint_text}\n"
                f"Run `check_health()` for full status.\n"
            )
        elif status == "degraded":
            header = ""  # degraded is not critical
            footer = (
                f"\n---\nℹ️ **{r.name}**: using CLI fallback "
                f"(language server unavailable). Results may be less detailed. "
                f"Run `check_health()` for details."
            )

    return header, footer


def _filter_by_severity(
    diagnostics: list[Diagnostic], min_severity: str | None,
) -> list[Diagnostic]:
    """Filter diagnostics to only include those at or above min_severity."""
    if not min_severity:
        return diagnostics
    threshold = _SEVERITY_NAMES.get(min_severity.lower())
    if threshold is None:
        return diagnostics
    return [d for d in diagnostics if d.severity.value <= threshold]


async def validate(
    ws: Workspace,
    file_path: str | None = None,
    directory: str | None = None,
    extensions: list[str] | None = None,
    max_files: int = 100,
    min_severity: str | None = None,
) -> str:
    """Run LSP diagnostics on a file, directory, or entire workspace.

    - file_path → rich contextual diagnostics per error (definition, hover, fixes)
    - directory → bulk scan with plain diagnostics
    - neither → scan the workspace root
    - min_severity → filter: "error", "warning", "information", "hint"
    """
    header, footer = _get_health_hints(ws, file_path)

    if file_path:
        from codebrain.skills.contextual_diagnostics import (
            contextual_diagnostics as _ctx_diag,
        )

        contexts = await _ctx_diag(ws.reporter, Path(file_path))
        if min_severity:
            contexts = [
                c for c in contexts
                if _SEVERITY_NAMES.get(min_severity.lower(), 99)
                >= c.diagnostic.severity.value
            ]
        if not contexts:
            result = "No diagnostics found."
            return (header + result + footer) if header or footer else result
        result = "\n\n---\n\n".join(format_diagnostic_context(c) for c in contexts)
        return (header + result + footer) if header or footer else result

    from codebrain.tools.validation import validate_workspace as _validate_ws

    target = Path(directory) if directory else Path(ws.info.root_path)
    ext_set = set(extensions) if extensions else None
    results = await _validate_ws(ws.reporter, target, ext_set, max_files)
    all_diags: list[Diagnostic] = []
    for diags in results.values():
        all_diags.extend(diags)
    all_diags = _filter_by_severity(all_diags, min_severity)
    result = format_diagnostics(all_diags)
    return (header + result + footer) if header or footer else result


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

        sub_r = ws.reporter.get_reporter_for_file(Path(file_path))
        if sub_r is None:
            return f"No language server for {file_path}"
        from codebrain.tools.navigation import _get_lsp_reporter as _unwrap

        try:
            lsp_r = _unwrap(sub_r, Path(file_path))
        except TypeError:
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
        # Show surrounding source context around the definition
        span = read_source_span(defn.file_path, defn.range.start.line)
        if span:
            parts.append(f"\n**Definition context**:\n```\n{span}\n```")
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
    max_chars: int = 8192,
) -> str:
    """Get a symbol outline for a file, or a ranked repository map.

    - file_path → hierarchical document symbols
    - no file_path → workspace-wide repomap ranked by importance
    """
    if file_path and not Path(file_path).is_dir():
        from codebrain.tools.navigation import document_symbols as _symbols

        try:
            syms = await _symbols(ws.reporter, Path(file_path))
        except (TypeError, Exception):
            syms = []

        if syms:
            return format_document_symbols(syms)

        # Fallback: use tree-sitter index for this file
        if ws.index.is_built:
            nodes = ws.index.query(file_path=Path(file_path))
            if nodes:
                lines_out: list[str] = []
                for n in sorted(nodes, key=lambda x: x.line):
                    sig = f" — `{n.signature}`" if n.signature else ""
                    lines_out.append(
                        f"- **{n.name}** ({n.kind}) at line {n.line + 1}{sig}"
                    )
                return "\n".join(lines_out)

        return f"No symbols found in {file_path}."

    # Workspace-wide repomap (also used when file_path is a directory)
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
    from codebrain.tools.navigation import _get_lsp_reporter

    sub_r = ws.reporter.get_reporter_for_file(Path(file_path))
    if sub_r is None:
        return f"No language server for {file_path}"
    try:
        lsp_r = _get_lsp_reporter(sub_r, Path(file_path))
    except TypeError:
        return f"No language server for {file_path}"

    parts: list[str] = []

    if check_signature:
        from codebrain.skills.signature_check import signature_check as _sig_check

        result = await _sig_check(lsp_r, Path(file_path), line, character)
        impact = result.impact
        hover_info = result.hover_info
        broken_diags = result.broken_diagnostics
    else:
        from codebrain.skills.impact_analysis import impact_analysis as _impact

        impact, broken_diags = await _impact(lsp_r, Path(file_path), line, character)
        hover_info = None

    # Symbol identity — always explicit
    symbol_name = impact.symbol_name or "(unknown)"
    defn_loc = impact.symbol_location
    parts.append(f"**Symbol**: `{symbol_name}`")
    parts.append(
        f"**Definition**: `{defn_loc.file_path}:{defn_loc.range.start}`"
    )

    if hover_info:
        parts.append(f"\n**Signature**:\n```\n{hover_info}\n```")

    # Usage summary with per-file breakdown
    parts.append(
        f"\n**Usages**: {impact.total_usages} "
        f"across {len(impact.affected_files)} files"
    )
    if impact.affected_files:
        # Count usages per file
        usage_by_file: dict[str, int] = {}
        for u in impact.usages:
            usage_by_file[u.file_path] = usage_by_file.get(u.file_path, 0) + 1
        for af in impact.affected_files[:10]:
            count = usage_by_file.get(af, 0)
            parts.append(f"  - `{af}` ({count} usages)")
        if len(impact.affected_files) > 10:
            parts.append(f"  - ... and {len(impact.affected_files) - 10} more files")

    # Top N usage locations with source lines
    if impact.usages:
        max_shown = 5
        shown = impact.usages[:max_shown]
        parts.append(f"\n**Top usage locations** (showing {len(shown)}/{impact.total_usages}):")
        for u in shown:
            source = _read_source_line(u.file_path, u.range.start.line)
            source_str = f"\n    > `{source[:100]}`" if source else ""
            parts.append(f"  - `{u.file_path}:{u.range.start}`{source_str}")

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
    scope: str = "definitions",
    max_results: int = 100,
) -> str:
    """Search for code by name or structural patterns via tree-sitter.

    - pattern_mode=True → tree-sitter S-expression query (requires language)
    - scope="definitions" (default) → symbol definitions (functions, classes, types)
    - scope="identifiers" → ALL identifier usages (method calls, variable refs, field access)
    - scope="all" → both definitions and identifier usages
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

    parts: list[str] = []

    # Symbol definitions
    if scope in ("definitions", "all"):
        from codebrain.tools.search import search_symbol as _search_sym

        symbols = await _search_sym(root, query, kind, language, max_results)
        if symbols:
            if scope == "all":
                parts.append("**Definitions:**")
            for s in symbols:
                sig = f" — `{s.signature}`" if s.signature else ""
                parts.append(
                    f"- **{s.name}** ({s.kind}) at `{s.file_path}:{s.line + 1}`{sig}"
                )

    # Identifier usages
    if scope in ("identifiers", "all"):
        from codebrain.tools.search import search_identifiers as _search_idents

        idents = await _search_idents(root, query, language, max_results)
        if idents:
            if scope == "all":
                parts.append(f"\n**Identifier usages** ({len(idents)}):")
            for m in idents:
                parts.append(f"- `{m.file_path}:{m.line + 1}`: `{m.context}`")

    if not parts:
        return "No matches found."
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# 6. debug_trace — "Debug this error"
# ---------------------------------------------------------------------------
async def debug_trace(
    ws: Workspace,
    stack_trace: str,
) -> str:
    """Parse a stack trace and enrich each frame with LSP context."""
    from codebrain.skills.stack_trace import analyze_stack_trace as _analyze
    from codebrain.skills.stack_trace import parse_stack_trace

    # Detect file extensions from the trace to pick the right reporter
    lsp_r = None
    frames = parse_stack_trace(stack_trace)
    for frame in frames:
        ext = Path(frame.file_path).suffix
        if ext:
            r = ws.reporter.get_reporter_for_file(Path(f"dummy{ext}"))
            if r is not None:
                lsp_r = r
                break

    # Fall back: any already-running reporter
    if lsp_r is None:
        for ext in ws.reporter.supported_extensions:
            r = ws.reporter.get_reporter_for_file(Path(f"dummy{ext}"))
            if r is not None and getattr(r, "is_running", False):
                lsp_r = r
                break

    if lsp_r is None:
        return "No language server available for stack trace analysis."

    # Unwrap to LSPReporter for stack trace analysis
    from codebrain.tools.navigation import _get_lsp_reporter

    try:
        lsp_reporter = _get_lsp_reporter(lsp_r, Path(frames[0].file_path) if frames else None)
    except TypeError:
        return "No language server available for stack trace analysis."
    result = await _analyze(lsp_reporter, stack_trace, Path(ws.info.root_path))
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
