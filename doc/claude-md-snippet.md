# CodeBrain CLAUDE.md Snippet

Copy the section below into your project's `CLAUDE.md`. The directives are intentionally strong —
Claude Code needs imperative rules to override its defaults.

---

## Code Intelligence (CodeBrain MCP)

This project has CodeBrain configured. It provides LSP-based type checking, symbol navigation, and structural search via MCP tools. These tools give you capabilities that built-in tools (Grep, Glob, Read) cannot: type-aware diagnostics, go-to-definition, find-all-references, call hierarchy, and impact analysis.

### MANDATORY Rules

1. **After editing any file, run `validate`** on it to catch type errors before moving on:
   ```
   validate(file_path="<the file you just edited>")
   ```
   This returns diagnostics with suggested fixes. Fix any errors before proceeding.

2. **Before modifying a function/class signature, run `check_impact`** to understand the blast radius:
   ```
   check_impact(file_path="<file>", line=<line>, character=<col>)
   ```
   This shows every caller and usage that would break. Plan your changes accordingly.

3. **When you need to understand what a symbol IS (type, definition, docs), use `explore_symbol`** — do NOT read the whole file and guess:
   ```
   explore_symbol(file_path="<file>", line=<line>, character=<col>)
   ```
   This returns the definition location, type signature, and docstring in one call.

4. **When you encounter a stack trace or error, use `debug_trace`** before manually reading files:
   ```
   debug_trace(stack_trace="<paste the full trace>")
   ```
   This enriches each frame with type info and definitions, so you understand the error faster.

### When to Prefer CodeBrain Over Built-in Tools

| Task | Do NOT do this | Do this instead |
|------|---------------|-----------------|
| Find where a function is defined | `Grep` for `def function_name` | `explore_symbol(file_path=..., symbol_query="function_name")` |
| Find all callers of a function | `Grep` for `function_name(` | `explore_symbol(..., include_callers=True)` |
| Check if your edit broke anything | Read files and hope | `validate(file_path="<edited file>")` |
| Understand a class before modifying it | Read the whole file | `outline(file_path="<file>")` then `explore_symbol` on specific members |
| Rename a symbol safely | Find-and-replace | `rename_symbol(file_path=..., line=..., character=..., new_name="...")` |
| Understand codebase structure | `Glob` + `Read` many files | `outline()` for a ranked workspace map |

### Tool Parameters Cheat Sheet

**`validate`** — Type-check code
- `file_path`: single file with rich context per error (definition + hover + fix suggestions)
- `directory` + `extensions` + `max_files`: bulk scan

**`explore_symbol`** — Look up any symbol
- Position mode: `file_path` + `line` + `character` (0-indexed)
- Name mode: `file_path` + `symbol_query` (fuzzy match)
- Flags: `include_references`, `include_callers`, `include_callees`

**`check_impact`** — What breaks if this symbol changes?
- `file_path` + `line` + `character` (required)
- `check_signature=True` (default) for full signature analysis

**`outline`** — Code structure
- With `file_path`: hierarchical symbol tree for that file
- Without `file_path`: ranked workspace-wide repository map

**`search`** — Find code
- Name search: `query` + optional `kind` (function, class, variable)
- Structural: `query` (tree-sitter pattern) + `language` + `pattern_mode=True`

**`rename_symbol`** — Safe rename across workspace
- `file_path` + `line` + `character` + `new_name`

**`debug_trace`** — Enrich a stack trace
- `stack_trace`: the full trace text (Python, JS, Go, C++, Rust supported)
