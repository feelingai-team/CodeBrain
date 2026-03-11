# CodeBrain Guide

CodeBrain is an open-source Python library and MCP server that gives coding agents LSP-based code validation and structural syntax search. It wraps Language Server Protocol servers and tree-sitter grammars into a clean, async Python API — usable as a direct SDK import or as an MCP plugin for any compatible agent.

## How CodeBrain Works

### Architecture

```
Consumers (Claude Code, Cursor, OpenHands, custom agents)
    │ MCP protocol          │ Python import
    ▼                       ▼
┌─ MCP Server (FastMCP) ──────────────────────────┐
├─ Skills (composed workflows) ────────────────────┤
├─ Tools (atomic operations) ──────────────────────┤
├─ LSP Engine ─────────┬─ Search (tree-sitter) ────┤
├─ Core (models, config, workspace management) ────┤
└──────────────────────────────────────────────────┘
```

CodeBrain operates in three layers:

**Tools** are single-purpose async functions. Each does one thing: validate a file, find references, search symbols. They talk directly to language servers or tree-sitter.

**Skills** compose multiple tools into higher-level workflows. For example, `contextual_diagnostics` validates a file, then for each error automatically fetches the definition, references, hover info, and suggested fixes — giving an agent everything it needs to fix the problem in one call.

**MCP Server** exposes 9 intent-oriented tools over the Model Context Protocol, each consolidating multiple atomic operations into what an LLM actually needs.

### Language Server Management

CodeBrain manages LSP servers as background processes. When you validate a Python file, CodeBrain:

1. Detects the language from the file extension
2. Finds or starts the appropriate language server (Pyright for Python)
3. Auto-discovers the project root (via `pyproject.toml`, `.git`, etc.)
4. Detects virtual environments and configures the Python path
5. Sends the file to the server and collects diagnostics
6. Translates LSP responses into Pydantic models

Servers start lazily on first use and stay alive for subsequent requests. The `MultiLanguageReporter` routes files to the correct server based on extension.

**Supported languages:**

| Language | Server | Extensions |
|----------|--------|------------|
| Python | Pyright | `.py`, `.pyi` |
| Go | gopls | `.go` |
| C/C++ | clangd | `.c`, `.cpp`, `.h`, `.hpp`, etc. |
| TypeScript | typescript-language-server | `.ts`, `.tsx` |
| JavaScript | typescript-language-server | `.js`, `.jsx` |

### Search Engine

CodeBrain uses tree-sitter for code-aware search, independent of language servers:

- **Symbol search**: Find functions, classes, types by name. Supports exact match, substring, glob patterns (`Motion*`), multi-keyword AND (`motion handler`), and pipe OR (`StreamParser|FrameParser`).
- **Identifier search**: Find all usages of a name — method calls, variable references, field access.
- **Structural search**: Tree-sitter S-expression queries for pattern matching across code structure.
- **Repomap**: PageRank-ranked symbol graph showing the most important symbols in a codebase.

### Incremental Indexing

CodeBrain maintains a symbol index that updates incrementally (~50-200ms per file change). With optional `watchfiles` integration, the index stays current as files change on disk.

---

## How to Use CodeBrain

### As an MCP Plugin

This is the primary usage mode. Any MCP-compatible agent (Claude Code, Cursor, OpenCode, custom) can connect.

#### Install

```bash
# From source
git clone https://github.com/feelingai-team/CodeBrain.git
cd CodeBrain
uv pip install -e ".[all]"
```

#### Register with Claude Code

```bash
# Global — available in every session
claude mcp add --transport stdio codebrain -- codebrain-mcp

# Or project-scoped — add .mcp.json to your repo root:
```

```json
{
  "mcpServers": {
    "codebrain": {
      "type": "stdio",
      "command": "codebrain-mcp",
      "args": []
    }
  }
}
```

#### Register with other agents

```bash
# OpenCode
opencode mcp add codebrain --type local --command "codebrain-mcp"

# Any MCP client — just run:
codebrain-mcp --workspace /path/to/project
```

#### Available MCP Tools

Once connected, your agent gets these 9 tools:

**`validate`** — Check code for errors.
- Pass a `file_path` for rich contextual diagnostics (with definitions, hover, fixes).
- Pass a `directory` for bulk scanning.
- Filter by `min_severity`: `"error"`, `"warning"`, `"information"`, `"hint"`.

**`explore_symbol`** — Deep-dive into a symbol.
- By position: `(file_path, line, character)` → definition + hover + references + call hierarchy.
- By name: `(file_path, symbol_query)` → fuzzy match from file outline, then resolve.
- Toggle `include_references`, `include_callers`, `include_callees`.

**`outline`** — Get code structure.
- With `file_path`: hierarchical document symbols for one file.
- Without: workspace-wide repomap ranked by importance (PageRank).

**`search`** — Find code by name or structure.
- Default mode searches symbol definitions (functions, classes, types).
- Set `mode: "identifiers"` for usages (calls, references).
- Set `mode: "pattern"` for tree-sitter structural queries.
- Supports `kind` filter (`function`, `class`, `type`), `language`, glob file paths.

**`check_impact`** — What breaks if a symbol changes?
- Shows all usages, affected files, and broken diagnostics.
- Suggests code actions for fixing breakage.

**`debug_trace`** — Parse and enrich stack traces.
- Supports Python, JS/TS, C/C++ (GDB), Go, Rust.
- Adds hover info, definitions, and reference counts per frame.
- Identifies likely root cause (deepest in-workspace frame).

**`rename_symbol`** — Rename across the workspace.
- Returns an edit list with all affected files.

**`add_workspace`** / **`list_workspaces`** — Manage workspace roots.

#### CLI Flags

```bash
codebrain-mcp --workspace /path/to/project --languages python typescript
```

| Flag | Description |
|------|-------------|
| `--workspace <path>` | Project root (default: current directory) |
| `--languages <lang ...>` | Limit to specific servers (e.g., `python typescript cpp go`) |

#### Project Scaffolding

```bash
codebrain init [directory] [--dry-run]
```

Auto-generates `.mcp.json`, `CLAUDE.md`, and hooks for a project.

---

### As a Python SDK

Import CodeBrain directly for custom tooling, scripts, or agent frameworks.

#### Install

```bash
uv pip install -e ".[all]"
# or specific extras:
uv pip install -e ".[search]"  # tree-sitter only
uv pip install -e ".[mcp]"     # MCP server only
```

#### Validate a file

```python
import asyncio
from codebrain.core.workspace import WorkspaceManager
from codebrain.tools.validation import validate_file

async def main():
    manager = WorkspaceManager()
    await manager.add_workspace("/path/to/project")
    workspace = manager.get_workspace_for_file("/path/to/project/main.py")

    diagnostics = await validate_file(workspace, "/path/to/project/main.py")
    for d in diagnostics:
        print(f"{d.severity.name}: {d.message} at line {d.range.start.line}")

asyncio.run(main())
```

#### Find references

```python
from codebrain.core.models import Position
from codebrain.tools.navigation import find_references

refs = await find_references(
    workspace,
    file_path="/path/to/project/main.py",
    position=Position(line=10, character=5),
)
for ref in refs:
    print(f"  {ref.file_path}:{ref.range.start.line}")
```

#### Search symbols

```python
from codebrain.tools.search import search_symbol

results = await search_symbol(
    workspace,
    query="handleRequest",
    kind="function",
    max_results=20,
)
```

#### Contextual diagnostics (skill)

```python
from codebrain.skills.contextual_diagnostics import contextual_diagnostics

contexts = await contextual_diagnostics(workspace, "/path/to/project/main.py")
for ctx in contexts:
    print(f"Error: {ctx.diagnostic.message}")
    if ctx.definition:
        print(f"  Defined at: {ctx.definition.file_path}:{ctx.definition.range.start.line}")
    for action in ctx.code_actions:
        print(f"  Fix: {action.title}")
```

#### Impact analysis (skill)

```python
from codebrain.skills.impact_analysis import impact_analysis

impact = await impact_analysis(
    workspace,
    file_path="/path/to/project/api.py",
    position=Position(line=15, character=4),
)
print(f"Symbol: {impact.symbol_name}")
print(f"Affected files: {impact.affected_files}")
for usage in impact.usages:
    print(f"  Used at: {usage.file_path}:{usage.range.start.line}")
```

#### Stack trace parsing (skill)

```python
from codebrain.skills.stack_trace import parse_and_enrich_trace

result = await parse_and_enrich_trace(
    workspace,
    trace_text="""Traceback (most recent call last):
  File "main.py", line 42, in handle
    process(data)
TypeError: process() missing 1 required argument""",
)
print(f"Root cause: {result.root_cause_frame}")
for frame in result.frames:
    print(f"  {frame.file}:{frame.line} {frame.function}")
```

### Data Models

All data flows through typed Pydantic models defined in `codebrain.core.models`:

- `Diagnostic` — error/warning with severity, code, source, range
- `DiagnosticContext` — diagnostic + definition + references + hover + code actions
- `DocumentSymbol` — hierarchical symbol with name, kind, range, children
- `SymbolLocation` — file path + range + optional name
- `SignatureChangeImpact` — usages and affected files for a changed symbol
- `RenameResult` — edit list with affected file count
- `CallHierarchyItem` / `CallHierarchyCall` — call graph nodes and edges

### Configuration

```python
from codebrain.core.config import ValidationConfig

config = ValidationConfig(
    python={"enabled": True, "error_action": "BLOCK", "warning_action": "WARN"},
    typescript={"enabled": True},
    cpp={"enabled": False},
    go={"enabled": True},
    diagnostic_timeout=30,
    parallel_file_limit=10,
)
```

Per-language settings:

| Setting | Description |
|---------|-------------|
| `enabled` | Toggle language server on/off |
| `lsp_command` | Custom server command override |
| `use_fallback` | Use Pyright CLI fallback (Python only) |
| `error_action` | `BLOCK` / `WARN` / `IGNORE` |
| `warning_action` | `BLOCK` / `WARN` / `IGNORE` |
| `pyrightconfig_path` | Custom Pyright config location |
| `tsconfig_path` | Custom tsconfig location |
| `compile_commands_path` | Custom compile_commands.json location |

---

## Prerequisites

CodeBrain requires the language servers to be installed on your system:

| Language | Install |
|----------|---------|
| Python | `npm install -g pyright` or `uv tool install pyright` |
| Go | `go install golang.org/x/tools/gopls@latest` |
| C/C++ | Install `clangd` via your system package manager |
| TypeScript/JS | `npm install -g typescript-language-server typescript` |

Tree-sitter grammars are bundled as Python packages and installed automatically with `.[search]` or `.[all]`.
