# CodeBrain-1

A code-based "brain" that dynamically adjusts plans and strategies through code generation.

## Benchmark Results

CodeBrain-1 achieves top-tier performance on [Terminal Bench 2.0](https://www.tbench.ai/) by 2026-02-10:

| Rank | Agent | Model | Accuracy |
|------|-------|-------|----------|
| 1 | Simple Codex | GPT-5.3-Codex | 75.1% ± 2.4 |
| 2 | **CodeBrain-1** | **GPT-5.3-Codex** | **70.3% ± 2.6** |
| 3 | Droid | Claude Opus 4.6 | 69.9% ± 2.5 |
| ... | ... | ... |

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

## Open Source Roadmap

We are currently focused on improving stability and efficiency. The planned release stages are:

- [ ] **Core module source code** - Late March 2026
- [ ] **Integration with popular agents** - TBD
