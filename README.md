# convomem-arena

**Conversational-memory tasks for agents, from [Salesforce ConvoMem](https://huggingface.co/datasets/Salesforce/ConvoMem), on verifiers v1.**

Each task asks a question about a user's earlier conversations with an assistant: a fact the user stated, something the assistant recommended, a detail that later changed, a preference to respect, or something that was never said at all. The answer is buried in a history that also holds many unrelated conversations from the same person. ConvoMem has 75,336 such items across 100 personas; tasks are built on the fly from the pinned dataset, so a run downloads only the files it needs.

The same tasks reach the agent in three ways, so long-context recall and agentic memory use are measured on identical data:

| `memory_mode` | What the agent gets | Tests |
|---|---|---|
| `context` (default) | The full history in the prompt, using ConvoMem's official answer prompt | Long-context recall (the paper's baseline) |
| `tools` | Only the question; the history sits behind a per-rollout MCP server with `memory_search` (BM25), `memory_read_conversation` and `memory_list_conversations` | Agentic retrieval: deciding what to look up, and when |
| `files` | Only the question; the history is written to `memory/conversation_NNN.txt` | Memory as a filesystem, with the harness's own tools |

Full documentation: **<https://rahmansunny071.github.io/convomem-arena/>** · Source: <https://github.com/rahmansunny071/convomem-arena>

## Quick start

```bash
prime env install memcova/convomem-arena

# check that tasks load (no model calls, no API key)
vf-validate convomem-arena -n 6 --only-setup --runtime.type subprocess

# run six episodes, one per category (agent and judge default to Prime Inference)
vf-run convomem-arena -n 6 -r 1 -m <model> \
  --env.agent.harness.id null --env.agent.runtime.type subprocess
```

Fully local, with one Ollama model as both agent and judge:

```bash
export OLLAMA_FAKE_KEY=unused
vf-run convomem-arena -n 6 -r 1 -m qwen3:30b-a3b \
  --client.base-url http://127.0.0.1:11434/v1 --client.api-key-var OLLAMA_FAKE_KEY \
  --env.agent.harness.id null --env.agent.runtime.type subprocess \
  --env.taskset.context-sizes 10 \
  --env.taskset.task.judge.base-url http://127.0.0.1:11434/v1 \
  --env.taskset.task.judge.api-key-var OLLAMA_FAKE_KEY \
  --env.taskset.task.judge.model qwen3:30b-a3b
```

## Categories

| Category | Tests | Graded against |
|---|---|---|
| `user_facts` | Recall of what the user said, possibly across several conversations | gold answer |
| `assistant_facts` | Recall of what the assistant said or recommended | gold answer |
| `changing_facts` | Only the latest value of something that changed | gold answer |
| `abstention` | Recognising that the answer was never given | refusal is RIGHT |
| `preferences` | Recommendations that respect stated preferences | rubric |
| `implicit_connections` | Connecting indirect context | rubric |

Tasks are interleaved across categories, so `-n 6` already covers all six. Evidence is mixed into same-persona filler with ConvoMem's official algorithm, seeded per task, keeping evidence order (which defines the answer for `changing_facts`).

## Scoring

- **Reward `correct`** (weight 1.0): 1.0 when the category's ConvoMem judge says RIGHT. The judge prompts are copied verbatim from the reference implementation, one per category. A reply with neither RIGHT nor WRONG **raises** instead of scoring 0, so a broken judge surfaces as an error.
- **Metrics** (`tools` mode, recorded, never rewarded): `memory_tool_calls`, `evidence_recall` (share of evidence conversations the agent retrieved) and `conversations_retrieved`. Low recall with a wrong answer is a search failure; high recall with a wrong answer is a reasoning failure.

## Configuration

| Flag | Default | Meaning |
|---|---|---|
| `--env.taskset.categories` | all six | Subset of categories |
| `--env.taskset.evidence-counts` | all | Keep items with these evidence counts (1–6) |
| `--env.taskset.context-sizes` | `1 10 30` | Conversations per history; one task per size per item (the paper uses up to 300) |
| `--env.taskset.seed` | `0` | Seeds item order and every mix |
| `--env.taskset.task.memory-mode` | `context` | `context`, `tools` or `files` |
| `--env.taskset.task.max-turns` | `40` | Model calls per rollout |
| `--env.taskset.task.judge.model` / `.base-url` / `.api-key-var` | Prime Inference | The judge endpoint |

The full reference is in the [documentation](https://rahmansunny071.github.io/convomem-arena/reference/configuration/).

## Notes

- **Sandbox shell harnesses.** With `bash` or any shell-capable harness on the `subprocess` runtime, the agent's shell runs on the evaluator host, which also holds the Hugging Face cache with gold answers. Use the `null` harness for `context` and `tools`, and `docker` or `prime` for `files` mode.
- **Keep the judge fixed** across compared runs; the rubric categories are especially sensitive to the judge model.
- **Comparable in protocol, not item for item:** samples are drawn here rather than taken from ConvoMem's pre-mixed test cases.

## Citation and license

If you use this environment, please cite ConvoMem: Salesforce AI Research, arXiv:2511.10523 (2025), BibTeX at <https://arxiv.org/abs/2511.10523>.

- **Dataset:** [Salesforce/ConvoMem](https://huggingface.co/datasets/Salesforce/ConvoMem), **CC-BY-NC-4.0** (non-commercial use only).
- **Judge prompts and mixing algorithm:** ported verbatim from [SalesforceAIResearch/ConvoMem](https://github.com/SalesforceAIResearch/ConvoMem), **Apache License 2.0**.
