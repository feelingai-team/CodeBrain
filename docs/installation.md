# Installation

## Claude Code

### One-liner (recommended)

```bash
claude mcp add --transport stdio codebrain -- uvx "codebrain[mcp,search]"
```

### Via plugin

```bash
/plugin install https://github.com/feelingai-team/CodeBrain
```

### Project-scoped (shared with team)

Add `.mcp.json` to your project root:

```json
{
  "mcpServers": {
    "codebrain": {
      "type": "stdio",
      "command": "uvx",
      "args": ["codebrain[mcp,search]"]
    }
  }
}
```

## OpenCode

Add to your `opencode.json` (project root or `~/.config/opencode/opencode.json`):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "codebrain": {
      "type": "local",
      "command": ["uvx", "codebrain[mcp,search]"],
      "enabled": true
    }
  }
}
```

Or via CLI:

```bash
opencode mcp add codebrain --type local --command "uvx codebrain[mcp,search]"
```

## Manual install

```bash
pip install codebrain[mcp,search]
codebrain-mcp --workspace /path/to/project
```

Or with `uv`:

```bash
uv pip install codebrain[all]
codebrain-mcp --workspace /path/to/project
```

## Available tools

Once connected, the following MCP tools are available:

| Tool | Description |
|------|-------------|
| `validate` | Check code for errors (single file or directory scan) |
| `explore_symbol` | Get definition, type info, references, call hierarchy |
| `outline` | Symbol outline for a file, or ranked repository map |
| `check_impact` | Analyze what breaks if a symbol changes |
| `search` | Find symbols by name or structural patterns |
| `debug_trace` | Parse stack traces with LSP context enrichment |
| `rename_symbol` | Rename a symbol across the workspace |
| `add_workspace` | Add a new workspace root |
| `list_workspaces` | List active workspaces |

## CLI options

```bash
codebrain-mcp [--workspace <path>] [--languages <lang1> <lang2> ...]
```

- `--workspace` — Project root (default: current directory)
- `--languages` — Limit to specific language servers (e.g. `python typescript cpp`)
