# CodeBrain-1

A code-based "brain" that dynamically adjusts plans and strategies through code generation.

![](./assets/cover.png)

## Benchmark Results

CodeBrain-1 achieves top-tier performance on [Terminal Bench 2.0](https://www.tbench.ai/) by 2026-02-10:

![](./assets/leaderboard.png)

On a focused subset of 47 coding tasks, CodeBrain-1 scores **72.3%**, demonstrating consistent code generation and execution capabilities.

## Tech Highlights

### Effective Context Searching

CodeBrain utilizes the code and symbol cross-referencing and indexing mechanisms provided by the Language Server Protocol (LSP) to efficiently and accurately retrieve information relevant to coding tasks, thereby enhancing the accuracy of large language models (LLMs) in program synthesis and problem-solving.

### Validation Feedback

CodeBrain further leverages the diagnostic capabilities of the Language Server Protocol (LSP) and, grounded in engineering expertise and task-specific characteristics, performs filtering, aggregation, and contextual information retrieval over LSP diagnostic outputs, thereby significantly reducing the overhead of the code–verify (or code–check) iteration loop.

## Use Case: Runtime Code Generation for Gameplay

### An Example

In search–engage–withdraw–style games, if a player repeatedly follows a habitual route and is observed multiple times, opposing groups can gradually reinforce a form of collective memory associated with that behavior.

On map construction phases, the system adjusts its global strategy accordingly by generating related code using CodeBrain. For example, the resources may be allocated as follows:

```
distribute(
  area = calculate_area(spots=player.history_hotspots),
  count = 0.7 * total,
)
```

## Install as MCP Plugin

CodeBrain exposes 9 tools (validate, outline, search, explore_symbol, check_impact, debug_trace, rename_symbol, add_workspace, list_workspaces) via the [Model Context Protocol](https://modelcontextprotocol.io/). Any MCP-compatible agent can use them.

### Claude Code

**One-liner (recommended):**

```bash
claude mcp add --transport stdio codebrain -- uvx "codebrain[mcp,search]"
```

This registers CodeBrain globally. It will be available in every Claude Code session.

**Project-scoped** (shared with your team via git) — add `.mcp.json` to your project root:

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

**Verify it works** — start a new Claude Code session and run:

```
/mcp
```

You should see `codebrain` listed with 9 tools.

### OpenCode

```bash
opencode mcp add codebrain --type local --command "uvx codebrain[mcp,search]"
```

Or add to `opencode.json` (project root or `~/.config/opencode/opencode.json`):

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

### Manual / Other Agents

```bash
pip install codebrain[mcp,search]
codebrain-mcp --workspace /path/to/project
```

The server communicates over stdio using the MCP JSON-RPC protocol. Point any MCP client at this command.

| Flag | Description |
|------|-------------|
| `--workspace <path>` | Project root (default: current directory) |
| `--languages <lang ...>` | Limit to specific language servers (e.g. `python typescript cpp`) |

See [doc/installation.md](doc/installation.md) for the full reference.

## Open Source Roadmap

We are currently focused on improving stability and efficiency. The planned release stages are:

- [ ] **Core module source code** - Late March 2026
- [ ] **Integration with popular agents** - TBD
