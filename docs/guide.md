# CodeBrain Guide

CodeBrain is an open-source Python library and MCP server that gives coding agents LSP-based code validation and structural syntax search. It wraps Language Server Protocol servers and tree-sitter grammars into a clean, async Python API — usable as a direct SDK import or as an MCP plugin for any compatible agent.

---

## Table of Contents

- [How CodeBrain Works](#how-codebrain-works)
  - [Architecture](#architecture)
  - [Language Server Management](#language-server-management)
  - [Search Engine](#search-engine)
  - [Incremental Indexing](#incremental-indexing)
- [How to Use CodeBrain](#how-to-use-codebrain)
  - [As an MCP Plugin](#as-an-mcp-plugin)
  - [As a Python SDK](#as-a-python-sdk)
- [Reference](#reference)
  - [MCP Tools Quick Reference](#mcp-tools-quick-reference)
  - [SDK Skills](#sdk-skills)
  - [Data Models](#data-models)
  - [Configuration](#configuration)
  - [Prerequisites](#prerequisites)

---

## How CodeBrain Works

### Architecture

```
Consumers (Claude Code, Cursor, OpenCode, custom agents)
    │ MCP protocol          │ Python import
    ▼                       ▼
┌─ Layer 5: MCP Server (FastMCP) ─────────────────┐
├─ Layer 4: Skills (composed workflows) ──────────┤
├─ Layer 3: Tools (atomic operations) ────────────┤
├─ Layer 2a: LSP Engine ─┬─ Layer 2b: Search ────┤
├─ Layer 1: Core (models, config, workspace) ─────┤
└─────────────────────────────────────────────────┘
```

CodeBrain operates in three layers:

| Layer | What it does | Example |
|-------|-------------|---------|
| **Tools** | Single-purpose async functions. Each does one thing. | `validate_file`, `find_references`, `search_symbol` |
| **Skills** | Compose multiple tools into higher-level workflows. | `contextual_diagnostics` = validate + definition + hover + code actions |
| **MCP Server** | Exposes 11 intent-oriented tools over MCP, each consolidating multiple atomic operations into what an LLM actually needs. | `validate`, `explore_symbol`, `search` |

### Language Server Management

CodeBrain manages LSP servers as background processes. When you validate a file, CodeBrain:

```
File (e.g. main.py)
  │
  ├─ 1. Detect language from extension
  ├─ 2. Find or start the appropriate language server
  ├─ 3. Auto-discover project root (pyproject.toml, .git, go.mod, etc.)
  ├─ 4. Detect virtualenvs / configure language paths
  ├─ 5. Send file to server, collect diagnostics
  └─ 6. Translate LSP responses → Pydantic models
```

Servers start **lazily** on first use and stay alive for subsequent requests. The `MultiLanguageReporter` routes files to the correct server by extension.

#### Supported Languages

| Language | LSP Server | Extensions | Notes |
|----------|-----------|------------|-------|
| Python | Pyright | `.py`, `.pyi` | Auto-detects virtualenvs |
| Go | gopls | `.go` | |
| C/C++ | clangd | `.c`, `.cc`, `.cpp`, `.cxx`, `.h`, `.hpp`, `.hxx` | Uses `compile_commands.json` |
| TypeScript | typescript-language-server | `.ts`, `.tsx` | Shared server with JS |
| JavaScript | typescript-language-server | `.js`, `.jsx` | Shared server with TS |

### Search Engine

CodeBrain uses tree-sitter for code-aware search, independent of language servers:

| Mode | What it finds | Example query |
|------|--------------|---------------|
| **Symbol search** | Functions, classes, types by name | `"handleRequest"`, `"Motion*"` (glob), `"motion handler"` (AND), `"StreamParser\|FrameParser"` (OR) |
| **Identifier search** | All usages — method calls, variable refs, field access | `"ctx"` finds every usage of `ctx` |
| **Structural search** | Tree-sitter S-expression pattern matching | `(function_definition name: (identifier) @name)` |
| **Repomap** | PageRank-ranked symbol graph of most important symbols | (no query — whole workspace) |

### Incremental Indexing

CodeBrain maintains a symbol index that updates incrementally (~50–200ms per file change). With optional `watchfiles` integration, the index stays current as files change on disk.

---

## How to Use CodeBrain

### As an MCP Plugin

This is the primary usage mode. Any MCP-compatible agent (Claude Code, Cursor, OpenCode, custom) can connect.

#### Install

```bash
pip install "codebrain[all] @ git+https://github.com/feelingai-team/CodeBrain.git"
```

Verify the installation:

```bash
codebrain-mcp --help
```

> **For contributors** — clone and install in editable mode instead:
> ```bash
> git clone https://github.com/feelingai-team/CodeBrain.git
> cd CodeBrain
> pip install -e ".[all]"
> ```

#### Register with Your Agent

| Agent | Registration |
|-------|-------------|
| **Claude Code** (global) | `claude mcp add --transport stdio codebrain -- codebrain-mcp` (verify: `/mcp` should list codebrain with 11 tools) |
| **Claude Code** (project) | Add `.mcp.json` to repo root (see below) |
| **OpenCode** (CLI) | `opencode mcp add codebrain --type local --command "codebrain-mcp"` |
| **OpenCode** (config) | Add to `opencode.json` (see below) |
| **Other clients** | `codebrain-mcp --workspace /path/to/project` |

<details>
<summary><b>.mcp.json</b> (Claude Code project-scoped)</summary>

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

</details>

<details>
<summary><b>opencode.json</b></summary>

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "codebrain": {
      "type": "local",
      "command": ["codebrain-mcp"],
      "enabled": true
    }
  }
}
```

</details>

#### Available MCP Tools

Once connected, your agent gets these **11 tools**:

##### Validation & Diagnostics

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| **`validate`** | Check code for errors. Pass `file_path` for rich per-error context (with definitions, hover, fixes), or `directory` for bulk scanning. | `file_path`, `directory`, `min_severity` (`"error"` / `"warning"` / `"information"` / `"hint"`) |

##### Code Navigation

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| **`explore_symbol`** | Deep-dive into a symbol: definition, type info, references, call hierarchy. Use `(line, character)` for position-based lookup, or `symbol_query` for name matching. | `file_path`, `line`, `character`, `symbol_query`, `include_references`, `include_callers`, `include_callees` |
| **`outline`** | With `file_path`: hierarchical document symbols. Without: workspace-wide repomap ranked by PageRank. | `file_path`, `max_chars` |
| **`check_impact`** | What breaks if a symbol changes? Shows usages, affected files, broken diagnostics, and suggested fixes. | `file_path`, `line`, `character`, `check_signature` |
| **`rename_symbol`** | Rename across the workspace. Returns an edit list with all affected files. | `file_path`, `line`, `character`, `new_name` |

##### Search

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| **`search`** | Find code by name or structure. Default searches symbol definitions. Use `scope="identifiers"` for usages (calls, refs). Use `scope="all"` for both. Set `pattern_mode=True` for tree-sitter structural queries. | `query`, `scope`, `pattern_mode`, `kind`, `language`, `file_paths` |

Query syntax:

```
search(query="HandleMotion")               # exact/substring match
search(query="motion handler")             # multi-keyword AND
search(query="StreamParser|FrameParser")   # pipe OR (best match wins)
search(query="Motion*")                    # glob pattern
search(query="...", pattern_mode=True)     # tree-sitter S-expression
```

##### Debugging

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| **`debug_trace`** | Parse and enrich stack traces. Supports Python, JS/TS, C/C++ (GDB), Go, Rust. Adds hover info, definitions, and reference counts per frame. Identifies likely root cause (deepest in-workspace frame). | `stack_trace` |

##### Workspace Management

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| **`add_workspace`** | Add a new workspace root. | `root_path` |
| **`list_workspaces`** | List all active workspaces. | — |
| **`check_health`** | Check language server health for all sub-projects. Returns status (active/degraded/unavailable) per language with remediation hints. | `workspace_path` |
| **`list_subprojects`** | List all detected sub-projects with their languages and markers. | `workspace_path` |

#### CLI Flags

```bash
codebrain-mcp --workspace /path/to/project --languages python typescript
```

| Flag | Description | Default |
|------|-------------|---------|
| `--workspace <path>` | Project root | Current directory |
| `--languages <lang ...>` | Limit to specific servers | All supported |

#### Project Scaffolding

```bash
codebrain init [directory] [--dry-run]
```

Auto-generates `.mcp.json`, `CLAUDE.md`, and hooks for a project.

#### CLAUDE.md SOPs (Recommended)

Copy the SOPs from [claude-md-snippet.md](claude-md-snippet.md) into your project's `CLAUDE.md`. This teaches Claude Code (and other agents that read CLAUDE.md) to use CodeBrain tools in a structured workflow — validate after every edit, check impact before modifying signatures, etc.

---

### As a Python SDK

Import CodeBrain directly for custom tooling, scripts, or agent frameworks.

#### Install

```bash
pip install "codebrain[all] @ git+https://github.com/feelingai-team/CodeBrain.git"

# or specific extras:
pip install "codebrain[search] @ git+https://github.com/feelingai-team/CodeBrain.git"  # tree-sitter only
pip install "codebrain[mcp] @ git+https://github.com/feelingai-team/CodeBrain.git"     # MCP server only
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

#### Stack trace analysis (skill)

```python
from codebrain.skills.stack_trace import analyze_stack_trace

result = await analyze_stack_trace(
    reporter=workspace.reporter,
    stack_trace="""Traceback (most recent call last):
  File "main.py", line 42, in handle
    process(data)
TypeError: process() missing 1 required argument""",
    workspace_root=workspace.info.root_path,
)
print(f"Root cause frame: {result.frames[result.root_cause_index].frame.file_path}")
for ef in result.frames:
    print(f"  {ef.frame.file_path}:{ef.frame.line} {ef.frame.function_name}")
```

---

## Reference

### MCP Tools Quick Reference

| # | Tool | Purpose | Category |
|---|------|---------|----------|
| 1 | `validate` | Check code for errors (single file or bulk) | Diagnostics |
| 2 | `explore_symbol` | Definition + hover + references + call hierarchy | Navigation |
| 3 | `outline` | File symbols or workspace-wide repomap | Navigation |
| 4 | `check_impact` | What breaks if a symbol changes | Navigation |
| 5 | `rename_symbol` | Rename across workspace | Navigation |
| 6 | `search` | Find symbols, identifiers, or structural patterns | Search |
| 7 | `debug_trace` | Parse and enrich stack traces | Debugging |
| 8 | `add_workspace` | Add a workspace root | Admin |
| 9 | `list_workspaces` | List active workspaces | Admin |
| 10 | `check_health` | Language server health per sub-project | Admin |
| 11 | `list_subprojects` | Detected sub-projects and their languages | Admin |

### SDK Skills

Skills compose multiple tools into higher-level workflows:

| Skill | Module | Composes | Description |
|-------|--------|----------|-------------|
| `contextual_diagnostics` | `codebrain.skills.contextual_diagnostics` | validate + definition + references + hover + code_actions | Validate and gather full fix context per diagnostic |
| `impact_analysis` | `codebrain.skills.impact_analysis` | find_references + validate | For a changed symbol, find all usages and check for breakage |
| `signature_check` | `codebrain.skills.signature_check` | impact_analysis + hover | Detect signature changes and downstream impact |
| `look_then_jump` | `codebrain.skills.look_then_jump` | outline + goto_definition + hover | Outline a file, find a symbol by name, jump to its definition |
| `analyze_stack_trace` | `codebrain.skills.stack_trace` | parse + hover + definition + references | Parse stack traces and enrich frames with LSP context |

### Data Models

All data flows through typed Pydantic models defined in `codebrain.core.models`:

| Model | Description |
|-------|-------------|
| `Diagnostic` | Error/warning with severity, code, source, range |
| `DiagnosticContext` | Diagnostic + definition + references + hover + code actions |
| `DocumentSymbol` | Hierarchical symbol with name, kind, range, children |
| `SymbolLocation` | File path + range + optional name |
| `SignatureChangeImpact` | Usages and affected files for a changed symbol |
| `RenameResult` | Edit list with affected file count |
| `CallHierarchyItem` | Call graph node (symbol with kind, URI, range) |
| `CallHierarchyCall` | Call graph edge (from/to item + call site ranges) |

### Configuration

```python
from codebrain.core.config import ValidationConfig

config = ValidationConfig(
    workspace_root="/path/to/project",
    python={"enabled": True, "error_action": "BLOCK", "warning_action": "WARN"},
    typescript={"enabled": True},
    cpp={"enabled": False},
    go={"enabled": True},
    diagnostic_timeout=30,
    parallel_file_limit=10,
)
```

#### Per-Language Settings

| Setting | Type | Description |
|---------|------|-------------|
| `enabled` | `bool` | Toggle language server on/off |
| `lsp_command` | `list[str]` | Custom server command override |
| `use_fallback` | `bool` | Use Pyright CLI fallback (Python only) |
| `error_action` | `str` | `"block"` / `"warn"` / `"ignore"` |
| `warning_action` | `str` | `"block"` / `"warn"` / `"ignore"` |
| `pyrightconfig_path` | `str` | Custom Pyright config location (Python) |
| `tsconfig_path` | `str` | Custom tsconfig location (TS/JS) |
| `compile_commands_path` | `str` | Custom compile_commands.json location (C/C++) |

### Prerequisites

CodeBrain requires the language servers to be installed on your system:

| Language | Install Command |
|----------|----------------|
| Python | `npm install -g pyright` or `uv tool install pyright` |
| Go | `go install golang.org/x/tools/gopls@latest` |
| C/C++ | Install `clangd` via your system package manager |
| TypeScript/JS | `npm install -g typescript-language-server typescript` |

Tree-sitter grammars are bundled as Python packages and installed automatically with `.[search]` or `.[all]`.
