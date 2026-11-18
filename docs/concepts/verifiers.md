---
title: "verifiers, prime-envs and the Hub"
description: "How convomem-arena maps onto Prime Intellect's verifiers v1 concepts, and what happens in one rollout."
---

# verifiers, prime-envs and the Hub

| Piece | Role | In this project |
|---|---|---|
| **verifiers** (`import verifiers.v1 as vf`) | Framework: tasks, tools, judges, rewards, and the runner that puts an agent on a task and records a trace | Every class here subclasses a `vf.*` base |
| **prime-envs** | Prime Intellect's repo of first-party environments; the source of conventions (layout, prompting rules, README style) | This package follows those conventions and can drop in as `environments/<group>/convomem_arena` |
| **Environments Hub** | Registry where environment packages are published and installed by ID (`owner/name@version`) | Packaged as `convomem-arena`, the ID it would be installed by |

> **verifiers v0 vs. v1.** Older tutorials and many Hub environments (listed as *Legacy*) use the v0 API: `load_environment()`, `vf.SingleTurnEnv`, `vf.ToolEnv`, `vf-eval`. The current release (`verifiers>=0.4.1`) ships only **v1**: `Taskset` / `Task` / `TaskData`, `@vf.reward`, `vf.Toolset`, and the `vf-validate` / `vf-run` CLIs. This package is v1 only.

## verifiers v1 concepts, mapped to this code

| verifiers concept | What it is | Here |
|---|---|---|
| `vf.TaskData` | One immutable row: the `prompt` plus hidden fields for scoring | `ConvoMemData` in `models.py` |
| `vf.Task` | Behavior for one row: `setup`, stop conditions, toolsets, rewards, metrics | `ConvoMemTask` in `taskset.py` |
| `vf.Taskset` | Loader that yields tasks from `load()` | `ConvoMemTaskset` in `taskset.py` |
| `vf.TasksetConfig` | Load-time knobs → `--env.taskset.*` flags | `ConvoMemConfig` |
| `vf.TaskConfig` | Per-task runtime and scoring knobs → `--env.taskset.task.*` flags | `ConvoMemTaskConfig` |
| `vf.State` | Mutable per-rollout state shared between tool servers and scoring | `MemoryState` in `models.py` |
| `vf.Toolset` + `@vf.tool` | Custom tools served over MCP | `MemoryToolset` in `servers/memory.py` |
| `vf.Judge` | LLM grader: a prompt template plus a `parse` function | `ConvoMemJudge` and its subclasses in `judges.py` |
| `@vf.reward(weight=…)` | Score that adds `score × weight` to `trace.reward` | `correct` |
| `@vf.metric` | Logged measurement that never affects the reward | `memory` (tool calls, evidence recall) |
| `@vf.stop` | Predicate that ends the rollout early | `turn_limit` |
| Harness | Agent program that talks to the model (`null`, `bash`, `claude_code`, …), chosen at run time | Not fixed by this taskset |
| Runtime | Where the harness runs (`subprocess`, `docker`, `prime`), chosen at run time | Not fixed by this taskset |
| Trace | The full record of a rollout, saved to `traces.jsonl` | See [Reading results](../guides/reading-results.md) |

The taskset ID maps to the module: `convomem-arena` → `import convomem_arena` → the class listed in `__all__` (`ConvoMemTaskset`). That's the only thing `convomem_arena/__init__.py` does.

## Rollout lifecycle

```
ConvoMemTaskset.load() ──yields──▶ ConvoMemTask(ConvoMemData, ConvoMemTaskConfig)
                                          │
  1. Task.setup(trace, runtime)           │  records trace.info["convomem"];
                                          │  files mode: writes memory/conversation_NNN.txt
  2. Task.toolsets(config)                │  tools mode: launches one MemoryToolset per rollout,
                                          │  which loads the history in setup_task(task_data)
  3. Harness runs the model ◀────────────┘  prompt = TaskData.prompt; MCP tools if any;
       │                                     @vf.stop turn_limit checked before each model call
  4. Scoring
       ├─ @vf.metric memory    → memory_tool_calls, evidence_recall, conversations_retrieved
       └─ @vf.reward correct   → ConvoMem judge for the category → RIGHT = 1.0, WRONG = 0.0
                                          │
  5. Trace written to traces.jsonl ◀──────┘
```
