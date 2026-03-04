"""Markdown-first output formatters for LLM consumption."""

from __future__ import annotations

from codebrain.core.models import (
    CallHierarchyCall,
    Diagnostic,
    DiagnosticContext,
    DiagnosticSeverity,
    DocumentSymbol,
    RenameResult,
    SymbolLocation,
)

_SEVERITY_ICONS: dict[DiagnosticSeverity, str] = {
    DiagnosticSeverity.ERROR: "ERROR",
    DiagnosticSeverity.WARNING: "WARN",
    DiagnosticSeverity.INFORMATION: "INFO",
    DiagnosticSeverity.HINT: "HINT",
}


def format_diagnostics(diagnostics: list[Diagnostic]) -> str:
    """Format diagnostics as Markdown for LLM consumption."""
    if not diagnostics:
        return "No diagnostics found."

    lines: list[str] = []
    for diag in diagnostics:
        severity = _SEVERITY_ICONS.get(diag.severity, "UNKNOWN")
        code_str = f" [{diag.code}]" if diag.code else ""
        source_str = f" ({diag.source})" if diag.source else ""
        loc = f"{diag.file_path}:{diag.range.start}"
        lines.append(f"- **{severity}**{code_str}{source_str} at `{loc}`: {diag.message}")
    return "\n".join(lines)


def format_diagnostic_context(ctx: DiagnosticContext) -> str:
    """Format full diagnostic context with DEF/REF/hover info."""
    parts: list[str] = []

    # Diagnostic itself
    diag = ctx.diagnostic
    severity = _SEVERITY_ICONS.get(diag.severity, "UNKNOWN")
    code_str = f" [{diag.code}]" if diag.code else ""
    parts.append(f"### {severity}{code_str}: {diag.message}")
    parts.append(f"Location: `{diag.file_path}:{diag.range.start}`")

    # Definition
    if ctx.definition:
        d = ctx.definition
        name = f" `{d.name}`" if d.name else ""
        parts.append(f"\n**Definition**{name}: `{d.file_path}:{d.range.start}`")

    # Hover info
    if ctx.hover_info:
        parts.append(f"\n**Type info**:\n```\n{ctx.hover_info}\n```")

    # References
    if ctx.references:
        parts.append(f"\n**References** ({len(ctx.references)}):")
        for ref in ctx.references:
            name = f" `{ref.name}`" if ref.name else ""
            parts.append(f"- `{ref.file_path}:{ref.range.start}`{name}")
        if ctx.references_truncated:
            parts.append(f"  _(truncated, limit={ctx.reference_limit})_")

    # Code actions
    if ctx.code_actions:
        parts.append("\n**Suggested fixes**:")
        for action in ctx.code_actions:
            preferred = " (preferred)" if action.is_preferred else ""
            parts.append(f"- {action.title}{preferred}")

    return "\n".join(parts)


def format_document_symbols(symbols: list[DocumentSymbol], indent: int = 0) -> str:
    """Format symbol outline as indented Markdown tree."""
    if not symbols:
        return "No symbols found."

    lines: list[str] = []
    prefix = "  " * indent
    for sym in symbols:
        detail = f" — {sym.detail}" if sym.detail else ""
        kind_name = sym.kind.name.lower()
        lines.append(f"{prefix}- **{sym.name}** ({kind_name}){detail}")
        if sym.children:
            lines.append(format_document_symbols(sym.children, indent + 1))
    return "\n".join(lines)


def format_call_hierarchy(calls: list[CallHierarchyCall], direction: str) -> str:
    """Format call hierarchy as Markdown list."""
    if not calls:
        return f"No {direction} calls found."

    lines = [f"**{direction.capitalize()} calls**:"]
    for call in calls:
        item = call.item
        detail = f" — {item.detail}" if item.detail else ""
        kind_name = item.kind.name.lower()
        loc = f"{item.file_path}:{item.range.start}"
        lines.append(f"- `{item.name}` ({kind_name}) at `{loc}`{detail}")
    return "\n".join(lines)


def format_rename_result(result: RenameResult) -> str:
    """Format rename edits grouped by file."""
    if not result.edits:
        return "No rename edits."

    # Group by file
    by_file: dict[str, list[str]] = {}
    for edit in result.edits:
        by_file.setdefault(edit.file_path, []).append(
            f"  - L{edit.range.start.line + 1}: `{edit.new_text}`"
        )

    lines = [f"**Rename** ({result.files_affected} files affected):"]
    for file_path, edits in by_file.items():
        lines.append(f"- `{file_path}`:")
        lines.extend(edits)
    return "\n".join(lines)


def format_symbol_locations(locations: list[SymbolLocation]) -> str:
    """Format symbol locations as Markdown list."""
    if not locations:
        return "No locations found."

    lines: list[str] = []
    for loc in locations:
        name = f" `{loc.name}`" if loc.name else ""
        lines.append(f"- `{loc.file_path}:{loc.range.start}`{name}")
    return "\n".join(lines)
