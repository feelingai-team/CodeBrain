# CodeBrain CLAUDE.md Template

Copy the section below into your project's `CLAUDE.md` and adjust for your language/project.

---

## Standard Operating Procedures

Follow these step-by-step procedures for ALL implementation work. Execute each step in order — do not skip steps.

### SOP 1: Feature Implementation

**Step 1 — Map the codebase.** Run this yourself in the main conversation (not via sub-agents):
```
outline()
```
This returns a ranked workspace map. Use it to identify where your feature fits.

**Step 2 — Find related code.** Search for symbols related to your feature:
```
search(query="<relevant function or type name>")
```
For each key symbol, get its full type info:
```
explore_symbol(file_path="<file>", symbol_query="<name>")
```
Read files only after you've located them via search/explore.

**Step 3 — Analyze impact before coding.** For every function/class/interface you plan to modify:
```
check_impact(file_path="<file>", line=<line>, character=<col>)
```
This shows every caller and usage that will break. Do not skip this step.

**Step 4 — Implement, one file at a time.** For each file:

  4a. Make the edit.

  4b. Immediately run:
  ```
  validate(file_path="<the file you just edited>")
  ```
  4c. If errors: fix them and re-run `validate`. Do NOT move to the next file until clean.

  4d. For renames, use:
  ```
  rename_symbol(file_path="<file>", line=<line>, character=<col>, new_name="<new>")
  ```
  Never use Grep + Edit for renames.

**Step 5 — Final verification.**
```
validate(directory="<project root>")
```
Then run your project's build and test commands.

---

### SOP 2: Bug Fix & Debugging

**Step 1 — Collect evidence.**

  - If you have a stack trace:
    ```
    debug_trace(stack_trace="<full trace>")
    ```
    Do this BEFORE reading any files.

  - If no stack trace:
    ```
    validate(file_path="<suspected file>")
    ```

**Step 2 — Trace the call chain.**
```
explore_symbol(file_path="<file>", line=<line>, character=<col>, include_callers=True)
```
Follow callers upward to understand how the buggy code path is reached.

**Step 3 — Understand the buggy symbol.**
```
explore_symbol(file_path="<file>", line=<line>, character=<col>)
```
Returns definition, type signature, and documentation.

**Step 4 — Fix.** Edit the file, then immediately:
```
validate(file_path="<the file you just edited>")
```
Fix errors before touching another file.

**Step 5 — Verify.** If you changed any signatures:
```
check_impact(file_path="<file>", line=<line>, character=<col>)
```
Then run tests.

---

## Tool Quick Reference

| Tool | What it does | Key parameters |
|------|-------------|----------------|
| `outline` | Workspace map or file symbol tree | `file_path` (optional) |
| `search` | Find symbols by name | `query`, `kind`, `language` |
| `explore_symbol` | Definition + type info + callers | `file_path` + `line` + `character` (0-indexed), or `file_path` + `symbol_query` |
| `check_impact` | What breaks if symbol changes | `file_path` + `line` + `character` |
| `validate` | Type-check via LSP | `file_path` (single) or `directory` + `extensions` (bulk) |
| `rename_symbol` | Safe cross-workspace rename | `file_path` + `line` + `character` + `new_name` |
| `debug_trace` | Enrich stack trace with types | `stack_trace` (full text) |

**Note:** Sub-agents (Explore, Plan, feature-dev:code-explorer) cannot access these tools. Always run them yourself in the main conversation.

---

## PostToolUse Hook (Optional)

Add to `.claude/settings.json` for automatic validate reminders after file edits:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "FILE=$(cat | jq -r '.tool_input.file_path // empty'); EXT=\"your_extension_here\"; if [ -n \"$FILE\" ] && echo \"$FILE\" | grep -q \"\\.$EXT$\"; then echo \"[CodeBrain] You just edited $FILE. Run validate(file_path=\\\"$FILE\\\") NOW.\"; fi"
          }
        ]
      }
    ]
  }
}
```

Replace `your_extension_here` with your language's extension (e.g., `go`, `py`, `ts`).
