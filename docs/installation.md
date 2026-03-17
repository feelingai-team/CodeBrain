# Installation

## Prerequisites

CodeBrain requires language servers for the languages you want to analyze:

| Language | Install |
|----------|---------|
| Python | `npm install -g pyright` or `uv tool install pyright` |
| Go | `go install golang.org/x/tools/gopls@latest` |
| C/C++ | Install `clangd` via your system package manager |
| TypeScript/JS | `npm install -g typescript-language-server typescript` |

You only need the servers for the languages in your project.

## Step 1: Install CodeBrain

```bash
pip install "codebrain[all] @ git+https://github.com/feelingai-team/CodeBrain.git"
```

Or install specific extras:

```bash
pip install "codebrain[mcp] @ git+https://github.com/feelingai-team/CodeBrain.git"         # MCP server only
pip install "codebrain[search] @ git+https://github.com/feelingai-team/CodeBrain.git"       # tree-sitter search only
pip install "codebrain[mcp,search] @ git+https://github.com/feelingai-team/CodeBrain.git"   # both, without watchfiles
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

## Step 2: Register with Your Agent

### Claude Code

**Global** — available in every Claude Code session:

```bash
claude mcp add --transport stdio codebrain -- codebrain-mcp
```

**Project-scoped** — add `.mcp.json` to your project root (commits with your repo so teammates get it automatically):

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

Claude Code starts the MCP server in your project's working directory, so CodeBrain automatically targets the right codebase — no `--workspace` flag needed.

**Verify** — start a new Claude Code session and run:

```
/mcp
```

You should see `codebrain` listed with 9 tools.

### OpenCode

**CLI:**

```bash
opencode mcp add codebrain --type local --command "codebrain-mcp"
```

**Config file** — add to `opencode.json` (project root or `~/.config/opencode/opencode.json`):

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

### Other MCP Clients

Run the server directly:

```bash
codebrain-mcp --workspace /path/to/project
```

The server communicates over stdio using the MCP JSON-RPC protocol. Point any MCP client at this command.

## CLI Options

```bash
codebrain-mcp [--workspace <path>] [--languages <lang1> <lang2> ...]
```

| Flag | Description |
|------|-------------|
| `--workspace <path>` | Project root (default: current directory) |
| `--languages <lang ...>` | Limit to specific language servers (e.g. `python typescript cpp go`) |

## Step 3: Add CLAUDE.md SOPs (Recommended)

Copy the SOPs from [docs/claude-md-snippet.md](claude-md-snippet.md) into your project's `CLAUDE.md`. This teaches Claude Code (and other agents that read CLAUDE.md) to use CodeBrain tools in a structured workflow — validate after every edit, check impact before modifying signatures, etc.

## Available Tools

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

## Project Scaffolding

Auto-generate `.mcp.json`, `CLAUDE.md`, and hooks for a project:

```bash
codebrain init [directory] [--dry-run]
```
