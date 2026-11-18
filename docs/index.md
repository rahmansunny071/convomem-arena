---
title: "convomem-arena"
description: "A conversational-memory environment for models and personal assistants, built on verifiers v1 for the Prime Intellect Environments Hub."
hide:
  - toc
---

# convomem-arena

convomem-arena turns [Salesforce ConvoMem](https://huggingface.co/datasets/Salesforce/ConvoMem) ([paper](https://arxiv.org/abs/2511.10523), [reference code](https://github.com/SalesforceAIResearch/ConvoMem)) into tasks for evaluation and reinforcement learning. Each task asks a question about a user's earlier conversations with an assistant: a fact the user stated, something the assistant recommended, a detail that later changed, a preference to respect, or something that was never said at all. The answer is buried in a history that also holds many unrelated conversations from the same person.

The same tasks reach the agent in three ways, so you can measure **long-context recall** and **agentic memory use** on identical data:

| `memory_mode` | What the agent gets | Tests |
|---|---|---|
| `context` (default) | The full history in the prompt, using ConvoMem's official answer prompt | Long-context recall (the paper's baseline) |
| `tools` | Only the question; the history sits behind a per-rollout MCP memory server | Agentic retrieval: deciding what to look up, and when |
| `files` | Only the question; the history is written to `memory/conversation_NNN.txt` | Memory as a filesystem, with general-purpose tools |

Answers are graded by **ConvoMem's official RIGHT/WRONG judges**, one per category, and in `tools` mode the environment also measures **whether the agent actually retrieved the evidence**.

## Get started

<div class="grid cards" markdown>

-   :material-rocket-launch-outline: **Evaluate a model**

    ---

    Install, check that tasks load, and run your first episodes against a hosted or fully local model.

    [:octicons-arrow-right-24: Model quick start](getting-started/quickstart.md)

-   :material-robot-outline: **Evaluate a personal assistant**

    ---

    Let an assistant live through a persona's history, build its own memory, then answer from it. Vellum is the worked example.

    [:octicons-arrow-right-24: Assistant quick start](getting-started/personal-assistant.md)

</div>

## Explore

<div class="grid cards" markdown>

-   :material-shape-outline: **Concepts**

    ---

    How the environment maps onto verifiers, what the dataset holds, how a task is built, and how it is scored.

    [:octicons-arrow-right-24: verifiers, prime-envs and the Hub](concepts/verifiers.md)

-   :material-shield-check-outline: **Quality**

    ---

    Audit the data and stress-test the judges before you trust a number.

    [:octicons-arrow-right-24: Data quality](quality/data-quality.md) · [Judge robustness](quality/judge-robustness.md)

-   :material-book-open-variant: **Guides**

    ---

    Recipes for real experiments, reading traces, and running against a Vellum assistant.

    [:octicons-arrow-right-24: Running evaluations](guides/running-evaluations.md)

-   :material-cog-outline: **Reference**

    ---

    Every configuration flag, the package architecture, and known limitations.

    [:octicons-arrow-right-24: Configuration](reference/configuration.md)

</div>
