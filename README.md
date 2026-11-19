# convomem-arena

**A conversational-memory environment for agentic systems, built on [verifiers](https://github.com/PrimeIntellect-ai/verifiers) v1 for the Prime Intellect Environments Hub.**

convomem-arena turns [Salesforce ConvoMem](https://huggingface.co/datasets/Salesforce/ConvoMem) ([paper](https://arxiv.org/abs/2511.10523), [reference code](https://github.com/SalesforceAIResearch/ConvoMem)) into tasks for evaluation and RL. Each task asks a question about a user's earlier conversations with the assistant: a fact the user stated, something the assistant recommended, a detail that later changed, a preference to respect, or something that was never said at all. The agent has to find the answer in a history that also contains many unrelated conversations from the same person.

The same tasks can reach the agent in three ways. That lets you measure **long-context recall** and **agentic memory use** on identical data:

| `memory_mode` | What the agent gets | Tools | Tests |
|---|---|---|---|
| `context` (default) | The full history in the prompt, using ConvoMem's official answer prompt | none | Long-context recall (the paper's baseline) |
| `tools` | Only the question. The history sits behind a per-rollout MCP memory server | `memory_search`, `memory_read_conversation`, `memory_list_conversations` | Agentic retrieval: deciding what to look up, and when |
| `files` | Only the question. The history is written to `memory/conversation_NNN.txt` in the agent's workspace | Whatever the harness provides (e.g. `bash`) | Memory as a filesystem, with general-purpose tools |

Answers are graded by **ConvoMem's official RIGHT/WRONG LLM judges**, using the matching judge for each category. In `tools` mode the environment also measures **whether the agent actually retrieved the evidence**.

---

## Quick start: evaluate a model

Requirements: Python ≥ 3.11 and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/rahmansunny071/convomem-arena.git && cd convomem-arena
uv venv --python 3.12
uv pip install -e ".[dev]"

# 1. check that tasks load and set up, with no model calls and no API key
uv run vf-validate convomem-arena -n 6 --only-setup --runtime.type subprocess

# 2. run a few real episodes (needs a model + judge endpoint; defaults use PRIME_API_KEY)
export PRIME_API_KEY=...
uv run vf-run convomem-arena -n 6 -r 1 -m <model> \
  --env.agent.harness.id null --env.agent.runtime.type subprocess
```

`-n 6` already covers all six categories. **No API key?** The [quick start](docs/getting-started/quickstart.md#run-fully-local-with-ollama) also shows a fully local run with Ollama, using one model as both agent and judge.

## Quick start: evaluate a personal assistant

A personal assistant is never handed its history: it hears each conversation once, decides what to remember, and has to find it again later. `convomem_arena.vellum_eval` tests that with [Vellum](https://github.com/vellum-ai/vellum-assistant), an open-source assistant with its own memory system. It makes a Vellum instance live through one persona's conversations, lets it build its memory its own way, then asks the questions and grades the answers with the same official judges.

```bash
python -m convomem_arena.vellum_eval.run \
  --source /path/to/vellum-assistant \
  --instance vellum-rsi-eval --persona Small_Business_Owner \
  --per-category 2 --history-size 16
```

Use a dedicated, freshly hatched instance: the build restores snapshots over its workspace. The [assistant quick start](docs/getting-started/personal-assistant.md) covers the four stages, the requirements and how to read the result.

## Documentation

The full documentation is at **<https://rahmansunny071.github.io/convomem-arena/>**. The same pages live in [`docs/`](docs/):

| | |
|---|---|
| **Get started** | [Evaluate a model](docs/getting-started/quickstart.md) · [Evaluate a personal assistant](docs/getting-started/personal-assistant.md) |
| **Concepts** | [verifiers, prime-envs and the Hub](docs/concepts/verifiers.md) · [The dataset](docs/concepts/dataset.md) · [How a task is built](docs/concepts/tasks.md) · [Memory modes](docs/concepts/memory-modes.md) · [Scoring](docs/concepts/scoring.md) |
| **Quality** | [Data card](docs/quality/data-card.md) · [Data quality](docs/quality/data-quality.md) · [Judge robustness](docs/quality/judge-robustness.md) |
| **Guides** | [Running evaluations](docs/guides/running-evaluations.md) · [Reading results](docs/guides/reading-results.md) · [Use a Vellum assistant as the model](docs/guides/vellum-as-model.md) |
| **Reference** | [Configuration](docs/reference/configuration.md) · [Architecture](docs/reference/architecture.md) · [Development](docs/reference/development.md) · [Design decisions](docs/reference/design-decisions.md) · [Limitations](docs/reference/limitations.md) · [Troubleshooting](docs/reference/troubleshooting.md) · [Changelog](docs/reference/changelog.md) |

To preview the site locally: `uv pip install -e ".[docs]" && uv run mkdocs serve`.

## Citation and license

If you use this environment, please cite ConvoMem:

> ConvoMem, Salesforce AI Research, arXiv:2511.10523 (2025). Use the BibTeX from <https://arxiv.org/abs/2511.10523>.

- **Dataset:** [Salesforce/ConvoMem](https://huggingface.co/datasets/Salesforce/ConvoMem), **CC-BY-NC-4.0** (non-commercial use only).
- **Judge prompts and mixing algorithm:** ported verbatim from [SalesforceAIResearch/ConvoMem](https://github.com/SalesforceAIResearch/ConvoMem), **Apache License 2.0**.
