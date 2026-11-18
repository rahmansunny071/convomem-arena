"""convomem-arena: conversational memory tasks from Salesforce ConvoMem.

Each task gives a question about a user's past conversations with the assistant. The
evidence conversations are mixed among filler conversations of the same persona (the
official ConvoMem mixing), and the history reaches the agent in one of three ways:

- `context`: the whole history is in the prompt, as in the paper's long-context baseline.
- `tools`: the history is reachable only through a per-rollout memory MCP server
  (`memory_search`, `memory_read_conversation`, `memory_list_conversations`).
- `files`: the history is written into the agent's workspace as one file per
  conversation under `memory/`, for coding harnesses with their own file tools.

The final reply is graded by the official ConvoMem RIGHT/WRONG judge for its category.
For the three fact categories, `fact_scoring = "exact_match"` grades it deterministically
instead (`exact_match.py`), and the `exact_match` metric is recorded either way.
"""

from __future__ import annotations

import random
from collections.abc import Iterator
from typing import Literal

import verifiers.v1 as vf
from pydantic import Field

from convomem_arena.data import (
    CATEGORIES,
    REPO_ID,
    REVISION,
    Category,
    EvidenceItem,
    EvidenceStream,
    HubSource,
    format_context,
    format_conversation,
    mix,
    round_robin,
)
from convomem_arena.exact_match import FACT_CATEGORIES, exact_match
from convomem_arena.judges import format_evidence, judge_for
from convomem_arena.models import ConvoMemData, MemoryState
from convomem_arena.servers.memory import MemoryToolset

MemoryMode = Literal["context", "tools", "files"]
FactScoring = Literal["judge", "exact_match"]

SELF_REFERENCE = (
    'If the User in the conversations refers to themselves ("I", "me", "my"), they are '
    "the person being asked about. Be direct and factual."
)

# The official ConvoMem answer prompt (EvaluationUtils.getModelAnswerPrompt).
CONTEXT_PROMPT = """\
Answer the question based on the conversations below. If the User in the conversation refers to themselves ("I", "me", "my"), they are the person being asked about. Be direct and factual.

{context}

Question: {question}

Answer:"""

TOOLS_PROMPT = (
    "Answer the question based on your past conversations with the User. The {n} "
    "conversations, in chronological order, are available through the memory tools. "
    + SELF_REFERENCE
    + "\n\nQuestion: {question}"
)

FILES_PROMPT = (
    "Answer the question based on your past conversations with the User. The {n} "
    "conversations are stored in the `memory/` directory of your working directory, one "
    "file per conversation in chronological order (`conversation_001.txt` is the oldest). "
    + SELF_REFERENCE
    + " Reply with the answer as your final message."
    + "\n\nQuestion: {question}"
)

MEMORY_DIR = "memory"


class ConvoMemTaskConfig(vf.TaskConfig):
    memory_mode: MemoryMode = "context"
    """How the conversation history reaches the agent: `context`, `tools` or `files`."""
    judge: vf.JudgeConfig = vf.JudgeConfig()
    """Endpoint and model for the ConvoMem RIGHT/WRONG judge."""
    tools: vf.ToolsetConfig = vf.ToolsetConfig()
    """Placement of the per-rollout memory tool server (`tools` mode)."""
    max_turns: int = Field(40, ge=1)
    """Model calls allowed per rollout before it is stopped."""
    fact_scoring: FactScoring = "judge"
    """How `user_facts`, `assistant_facts` and `changing_facts` are rewarded: `judge`
    (the official ConvoMem judges, comparable with the paper) or `exact_match` (the
    deterministic check in `exact_match.py`: no judge call, cheap and stable for
    training). The other categories always use their judge."""


class ConvoMemTask(vf.Task[ConvoMemData, MemoryState, ConvoMemTaskConfig]):
    @property
    def key(self) -> str:
        return self.data.id or self.hash

    @classmethod
    def toolsets(cls, config: ConvoMemTaskConfig) -> list[vf.Toolset]:
        if config.memory_mode == "tools":
            return [MemoryToolset(config.tools)]
        return []

    async def setup(self, trace: vf.Trace, runtime: vf.Runtime) -> None:
        trace.info["convomem"] = {
            "category": self.data.category,
            "evidence_count": self.data.evidence_count,
            "context_size": self.data.context_size,
            "num_conversations": self.data.num_conversations,
            "memory_mode": self.config.memory_mode,
        }
        if self.config.memory_mode != "files":
            return
        for i, conversation in enumerate(self.data.conversations):
            text = format_conversation(conversation, i + 1) + "\n"
            await runtime.write(f"{MEMORY_DIR}/conversation_{i + 1:03d}.txt", text.encode())

    @vf.stop
    async def turn_limit(self, trace: vf.Trace) -> bool:
        return trace.num_turns >= self.config.max_turns

    def _exact_match(self, response: str) -> float:
        return exact_match(
            response,
            self.data.answer,
            self.data.question,
            self.data.category,
            self.data.evidence_messages,
        )

    @vf.reward(weight=1.0)
    async def correct(self, trace: vf.Trace) -> float:
        response = trace.last_reply or ""
        if not response.strip():
            return 0.0
        if self.config.fact_scoring == "exact_match" and self.data.category in FACT_CATEGORIES:
            return self._exact_match(response)
        judge = judge_for(self.data.category, self.data.evidence_count, self.config.judge)
        result = await judge.evaluate(
            trace=trace,
            question=self.data.question,
            answer=self.data.answer,
            response=response,
            evidence=format_evidence(
                self.data.category, self.data.evidence_count, self.data.evidence_messages
            ),
        )
        return float(result.parsed)

    @vf.metric
    async def deterministic(self, trace: vf.Trace) -> dict[str, float]:
        """The exact-match score for fact categories, recorded beside the reward whichever
        scorer the reward uses, so the two can be compared on every run."""
        if self.data.category not in FACT_CATEGORIES:
            return {}
        return {"exact_match": self._exact_match(trace.last_reply or "")}

    @vf.metric
    async def memory(self, trace: vf.Trace) -> dict[str, float]:
        """Tool-use and retrieval signals, recorded in `tools` mode only."""
        if self.config.memory_mode != "tools":
            return {}
        state = trace.state
        evidence = set(self.data.evidence_positions)
        found = evidence & set(state.retrieved)
        return {
            "memory_tool_calls": float(state.tool_calls),
            "evidence_recall": len(found) / len(evidence) if evidence else 0.0,
            "conversations_retrieved": float(len(state.retrieved)),
        }


class ConvoMemConfig(vf.TasksetConfig):
    categories: list[Category] = Field(default_factory=lambda: list(CATEGORIES))
    """Evidence categories to include."""
    evidence_counts: list[int] | None = None
    """Keep only these evidence counts (number of evidence conversations); all by default."""
    context_sizes: list[int] = Field(default_factory=lambda: [1, 10, 30])
    """Conversations per history; each item yields one task per size. The paper uses
    1, 2, 3, 4, 5, 6, 10, 20, 30, 50, 70, 100, 150, 200 and 300."""
    seed: int = 0
    """Seeds the item order and every mix."""
    repo_id: str = REPO_ID
    revision: str = REVISION
    task: ConvoMemTaskConfig = ConvoMemTaskConfig()


class ConvoMemTaskset(vf.Taskset[ConvoMemTask, ConvoMemConfig]):
    def load(self) -> Iterator[ConvoMemTask]:
        """Tasks interleaved across categories (and evidence counts within a category),
        so a small `-n` already covers every category. Files download lazily."""
        stream = EvidenceStream(
            HubSource(self.config.repo_id, self.config.revision), self.config.seed
        )
        items = round_robin(
            [stream.category_items(c, self.config.evidence_counts) for c in self.config.categories]
        )
        for item in items:
            filler = stream.filler(item.persona_file)
            for size in self.config.context_sizes:
                yield self.build(item, filler, size)

    def build(self, item: EvidenceItem, filler, context_size: int) -> ConvoMemTask:
        folder, _ = CATEGORIES[item.category]
        task_id = (
            f"{folder}/{item.evidence_count}_evidence/{item.persona_file.removesuffix('.json')}"
            f"/{item.item_index}/ctx{context_size}"
        )
        rng = random.Random(f"{self.config.seed}:{task_id}")
        conversations, positions = mix(item.conversations, filler, context_size, rng)
        mode = self.config.task.memory_mode
        if mode == "context":
            prompt = CONTEXT_PROMPT.format(
                context=format_context(conversations), question=item.question
            )
        else:
            template = TOOLS_PROMPT if mode == "tools" else FILES_PROMPT
            prompt = template.format(n=len(conversations), question=item.question)
        data = ConvoMemData(
            id=task_id,
            name=item.category,
            prompt=prompt,
            question=item.question,
            answer=item.answer,
            category=item.category,
            evidence_count=item.evidence_count,
            context_size=context_size,
            evidence_messages=item.evidence_messages,
            evidence_positions=positions,
            num_conversations=len(conversations),
            conversations=[] if mode == "context" else conversations,
        )
        return ConvoMemTask(data, self.config.task)
