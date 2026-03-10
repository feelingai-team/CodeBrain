"""Auto-generate CodeBrain configuration for a project."""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Mapping from marker files to language names
_LANGUAGE_MARKERS: dict[str, str] = {
    "pyproject.toml": "python",
    "setup.py": "python",
    "setup.cfg": "python",
    "requirements.txt": "python",
    "go.mod": "go",
    "tsconfig.json": "typescript",
    "package.json": "typescript",
    "CMakeLists.txt": "cpp",
    "compile_commands.json": "cpp",
    "Cargo.toml": "rust",
}



def detect_languages(root: Path, max_depth: int = 3) -> list[str]:
    """Detect languages present in a project by scanning for marker files."""
    found: set[str] = set()

    def _scan(directory: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            for entry in sorted(directory.iterdir()):
                name = entry.name
                if name.startswith(".") or name == "node_modules" or name == "vendor":
                    continue
                if entry.is_file() and name in _LANGUAGE_MARKERS:
                    found.add(_LANGUAGE_MARKERS[name])
                if entry.is_dir():
                    _scan(entry, depth + 1)
        except OSError:
            pass

    _scan(root, 0)
    return sorted(found)


def detect_subprojects(root: Path, max_depth: int = 3) -> list[dict[str, str]]:
    """Find sub-projects (directories with their own root markers)."""
    markers = {"pyproject.toml", "go.mod", "package.json", "tsconfig.json", "Cargo.toml",
               "CMakeLists.txt", "setup.py"}
    seen_dirs: set[str] = set()
    projects: list[dict[str, str]] = []

    def _scan(directory: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            for entry in sorted(directory.iterdir()):
                if entry.name.startswith(".") or entry.name in ("node_modules", "vendor", ".venv"):
                    continue
                if entry.is_file() and entry.name in markers:
                    rel = str(directory.relative_to(root)) if directory != root else "."
                    if rel not in seen_dirs:
                        seen_dirs.add(rel)
                        lang = _LANGUAGE_MARKERS.get(entry.name, "unknown")
                        projects.append({
                            "path": rel,
                            "language": lang,
                            "marker": entry.name,
                        })
                if entry.is_dir():
                    _scan(entry, depth + 1)
        except OSError:
            pass

    _scan(root, 0)
    return projects


def _detect_hook_extensions(languages: list[str]) -> str:
    """Build the file extension match pattern for PostToolUse hooks."""
    exts: set[str] = set()
    lang_to_exts = {
        "python": ["py"],
        "go": ["go"],
        "typescript": ["ts", "tsx", "js", "jsx"],
        "cpp": ["c", "cpp", "h", "hpp"],
        "rust": ["rs"],
    }
    for lang in languages:
        exts.update(lang_to_exts.get(lang, []))
    return " ".join(sorted(exts))


def generate_mcp_json(
    codebrain_path: str,
    languages: list[str],
) -> dict:
    """Generate .mcp.json content."""
    return {
        "mcpServers": {
            "codebrain": {
                "type": "stdio",
                "command": codebrain_path,
                "args": ["--languages"] + languages,
            }
        }
    }


def generate_settings_json(languages: list[str]) -> dict:
    """Generate .claude/settings.json with PostToolUse hooks."""
    exts = _detect_hook_extensions(languages)
    return {
        "hooks": {
            "PostToolUse": [
                {
                    "matcher": "Edit|Write",
                    "hooks": [
                        {
                            "type": "command",
                            "command": (
                                'FILE=$(cat | jq -r \'.tool_input.file_path // empty\'); '
                                'if [ -n "$FILE" ]; then '
                                'EXT="${FILE##*.}"; '
                                f'if echo "{exts}" | grep -qw "$EXT"; then '
                                'echo "[CodeBrain] You just edited $FILE. '
                                'Run validate(file_path=\\"$FILE\\") NOW to check for '
                                'type errors before proceeding."; fi; fi'
                            ),
                        }
                    ],
                }
            ]
        }
    }


def generate_claude_md(
    project_name: str,
    subprojects: list[dict[str, str]],
    languages: list[str],
) -> str:
    """Generate CLAUDE.md content."""
    parts: list[str] = []
    parts.append("# CLAUDE.md\n")
    parts.append(f"## Project Overview\n")
    parts.append(f"**{project_name}** — detected languages: {', '.join(languages)}\n")

    if subprojects:
        parts.append("| Sub-project | Language | Marker |")
        parts.append("|-------------|----------|--------|")
        for sp in subprojects:
            parts.append(f"| `{sp['path']}` | {sp['language']} | {sp['marker']} |")
        parts.append("")

    parts.append("""## Standard Operating Procedures

Follow these step-by-step procedures for ALL implementation work.

### SOP 1: Feature Implementation

**Step 1 — Map the codebase.**
```
outline()
```

**Step 2 — Find related code.**
```
search(query="HandleMotion")                  # exact/substring match
search(query="motion handler")                # multi-keyword AND
search(query="StreamParser|FrameParser")      # pipe OR (best match wins)
search(query="Motion*")                       # glob pattern
explore_symbol(file_path="<file>", symbol_query="<name>")
```

**Step 3 — Analyze impact before coding.** For every symbol you plan to modify:
```
check_impact(file_path="<file>", line=<line>, character=<col>)
```

**Step 4 — Implement, one file at a time.** After each edit:
```
validate(file_path="<the file you just edited>")
```
Fix errors before moving to the next file. For renames, use:
```
rename_symbol(file_path="<file>", line=<line>, character=<col>, new_name="<new>")
```

**Step 5 — Final verification.**
```
validate(directory="<affected sub-project path>")
```

### SOP 2: Bug Fix & Debugging

**Step 1 — Collect evidence.**
```
debug_trace(stack_trace="<paste the full traceback>")
```
Or: `validate(file_path="<suspected file>")`

**Step 2 — Trace the call chain.**
```
explore_symbol(file_path="<file>", line=<line>, character=<col>, include_callers=True)
```

**Step 3 — Fix and verify.** Edit, then:
```
validate(file_path="<the file you just edited>")
check_impact(file_path="<file>", line=<line>, character=<col>")
```

## Tool Quick Reference

| Tool | What it does |
|------|-------------|
| `outline` | Workspace map or file symbol tree |
| `search` | Find symbols by name or keywords (all must match) |
| `explore_symbol` | Definition + type info + callers |
| `check_impact` | What breaks if symbol changes |
| `validate` | Type-check via LSP |
| `rename_symbol` | Safe cross-workspace rename |
| `debug_trace` | Enrich stack trace with types |

**Note:** Sub-agents cannot access these tools. Always run them yourself.
""")

    return "\n".join(parts)


def init_project(
    root: Path,
    codebrain_command: str | None = None,
    dry_run: bool = False,
) -> str:
    """Initialize CodeBrain configuration in a project.

    Returns a summary of what was created/detected.
    """
    root = root.resolve()
    project_name = root.name

    # Detect languages and sub-projects
    languages = detect_languages(root)
    subprojects = detect_subprojects(root)

    if not languages:
        return f"No supported languages detected in {root}. Nothing to do."

    # Resolve codebrain-mcp path
    if codebrain_command is None:
        import shutil
        codebrain_command = shutil.which("codebrain-mcp") or "codebrain-mcp"

    lines: list[str] = []
    lines.append(f"CodeBrain init for: {root}")
    lines.append(f"Detected languages: {', '.join(languages)}")
    if subprojects:
        lines.append(f"Sub-projects found: {len(subprojects)}")
        for sp in subprojects:
            lines.append(f"  - {sp['path']} ({sp['language']}, {sp['marker']})")

    if dry_run:
        lines.append("\n[dry-run] Would create:")
    else:
        lines.append("\nCreated:")

    # .mcp.json
    mcp_path = root / ".mcp.json"
    mcp_content = generate_mcp_json(codebrain_command, languages)
    if not mcp_path.exists():
        if not dry_run:
            mcp_path.write_text(json.dumps(mcp_content, indent=2) + "\n")
        lines.append(f"  {mcp_path.relative_to(root)}")
    else:
        lines.append(f"  {mcp_path.relative_to(root)} (already exists, skipped)")

    # CLAUDE.md
    claude_md_path = root / "CLAUDE.md"
    if not claude_md_path.exists():
        claude_md = generate_claude_md(project_name, subprojects, languages)
        if not dry_run:
            claude_md_path.write_text(claude_md)
        lines.append(f"  {claude_md_path.relative_to(root)}")
    else:
        lines.append(f"  {claude_md_path.relative_to(root)} (already exists, skipped)")

    # .claude/settings.json
    settings_dir = root / ".claude"
    settings_path = settings_dir / "settings.json"
    if not settings_path.exists():
        settings = generate_settings_json(languages)
        if not dry_run:
            settings_dir.mkdir(exist_ok=True)
            settings_path.write_text(json.dumps(settings, indent=2) + "\n")
        lines.append(f"  {settings_path.relative_to(root)}")
    else:
        lines.append(f"  {settings_path.relative_to(root)} (already exists, skipped)")

    # Dependency readiness checks
    warnings: list[str] = []
    for sp in subprojects:
        sp_path = root / sp["path"]
        if sp["language"] == "python":
            if not (sp_path / ".venv").is_dir():
                warnings.append(
                    f"  ⚠ {sp['path']}: no .venv found — "
                    f"run `cd {sp['path']} && python -m venv .venv && pip install -e .`"
                )
        elif sp["language"] == "go":
            if not (sp_path / "vendor").is_dir() and (sp_path / "go.sum").exists():
                # go.sum exists but no vendor — modules need downloading
                pass  # gopls handles this via GOMODCACHE
        elif sp["language"] == "typescript":
            if not (sp_path / "node_modules").is_dir():
                warnings.append(
                    f"  ⚠ {sp['path']}: no node_modules — "
                    f"run `cd {sp['path']} && npm install`"
                )

    if warnings:
        lines.append("\nDependency warnings:")
        lines.extend(warnings)

    return "\n".join(lines)
