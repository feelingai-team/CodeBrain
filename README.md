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

CodeBrain exposes 11 tools (validate, outline, search, explore_symbol, check_impact, debug_trace, rename_symbol, add_workspace, list_workspaces, check_health, list_subprojects) via the [Model Context Protocol](https://modelcontextprotocol.io/). Any MCP-compatible agent can use them.

### Step 1: Install CodeBrain

```bash
pip install "codebrain[all] @ git+https://github.com/feelingai-team/CodeBrain.git"
```

This installs the `codebrain-mcp` command. Verify with:

```bash
codebrain-mcp --help
```

> **For contributors** — clone and install in editable mode instead:
> ```bash
> git clone https://github.com/feelingai-team/CodeBrain.git
> cd CodeBrain
> pip install -e ".[all]"
> ```

### Step 2: Register with Your Agent

#### Claude Code

**Global** — available in every session:

```bash
claude mcp add --transport stdio codebrain -- codebrain-mcp
```

**Project-scoped** — add `.mcp.json` to your project root (shared with your team via git):

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

**Verify** — start a new Claude Code session and run `/mcp`. You should see `codebrain` listed with 11 tools.

#### OpenCode

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

#### Other MCP Clients

```bash
codebrain-mcp --workspace /path/to/project
```

The server communicates over stdio using the MCP JSON-RPC protocol. Point any MCP client at this command.

| Flag | Description |
|------|-------------|
| `--workspace <path>` | Project root (default: current directory) |
| `--languages <lang ...>` | Limit to specific language servers (e.g. `python typescript cpp`) |

See [docs/guide.md](docs/guide.md) for the full reference, including SDK usage, CLAUDE.md integration, and all available tools.

## Open Source Roadmap

We are currently focused on improving stability and efficiency. The planned release stages are:

- [ ] **Core module source code** - Late March 2026
- [ ] **Integration with popular agents** - TBD
