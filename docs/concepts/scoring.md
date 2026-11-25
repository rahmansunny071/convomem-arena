---
title: "Scoring"
description: "The reward, ConvoMem's official per-category judges, and the retrieval metrics recorded in tools mode."
---

# Scoring

## Reward

| Name | Weight | Value |
|---|---|---|
| `correct` | 1.0 | `1.0` if the category's ConvoMem judge says RIGHT, else `0.0`. An empty final reply scores `0.0` without calling the judge. With `fact-scoring exact_match`, the three fact categories use the deterministic check below instead |

## Exact match for fact categories

!!! warning "A sanity check, not a benchmark score"
    Exact match is meant as a **cheap sanity check** that the environment runs end to end and that replies contain the expected facts, with no judge endpoint and no cost. **For any full-scale evaluation, published result or leaderboard, always use the official judges** (the default, `fact-scoring judge`), and keep the judge model fixed across compared runs.

The official judges make scores comparable with the ConvoMem paper, but each one is a model call: it costs time and money, needs an endpoint, and can vary between runs. For `user_facts`, `assistant_facts` and `changing_facts` there is a deterministic alternative.

ConvoMem's gold answers are full sentences, so a literal comparison almost never matches. Instead a reply **matches when it contains the answer's details**: the names and numbers the question doesn't already contain. *"The concert has been postponed to April 10th of next year"* needs `april` and `10`. Answers with no names or numbers fall back to their content words. The answer and the reply are read the same way: accents are dropped (*Brené* = *Brene*), dotted abbreviations closed (*a.m.* = *AM*), letters split from digits (*XY123456* = *XY 123456*), and numbers are compared only with numbers (*$2,100* is 2100, not 2 and 100).

Four guards keep it from being gamed when used as a training reward:

- **No dumping:** a reply longer than max(100, 5 × the answer's words) scores 0.
- **No candidate lists:** a reply scores 0 when it offers more than 8 names or numbers that neither the answer nor the question contains, 3 or more making up over half its words, 2 or more in a reply that is at least 75% names and numbers, or 3 or more new words with almost no function words (a list in lower case). *"Liam Petrov, Acme, Boston"* fails; *"Liam Petrov, from Acme Corp in Boston."* passes.
- **No hedging or denial:** a reply scores 0 when it voices doubt the answer doesn't (*I don't remember*, *I can't tell*, *no idea*, *maybe*, *not sure*, *wrong*; not remembering that the question itself voices, *I can't recall the exact day*, may be echoed), when the sentences stating the answer's details use *not*, *no*, *never*, *or*, *either*, *neither* or *n't* more often than the answer does (a lead-in before them counts a denial, *not*, *nor* or *neither*, and a sentence with *either … or*, beyond what the question has: *It is not this.*, *Not October, right?*; *No problem!*, *Not a problem!*, *Not to worry!*, *Either way* and a lone *or* don't count), or when a sentence of its own rejects or adds an alternative (*Nope.*, *That's not right.*, *That wasn't it.*, *Or October.*). An answer without names is stated by any sentence holding half the key words of one of its sentences, so a long answer is checked sentence by sentence too.
- **No stale numbers** (`changing_facts`): a reply that also states a number from an earlier evidence message, one the latest message and the answer no longer contain, scores 0. *"October 5th or April 10th"* fails; *"postponed from the original October date to April 10th"* passes.

It is recorded as the `exact_match` metric on every fact-category rollout, whatever the reward uses, so the two can be compared on any run. To make it the reward and skip the judge for those categories:

```bash
vf-run convomem-arena ... --env.taskset.task.fact-scoring exact_match
```

The other three categories always use their judge: abstention and the two rubric categories have no string to match.

**How well it agrees with the judge.** On 36 replies the judge had graded (24 from local runs and 12 from a Vellum memory evaluation), exact match gave the same verdict every time. Those were ordinary replies, so they say nothing about replies written to game the check.

**How hard it is to game.** [Issue #11](https://github.com/rahmansunny071/convomem-arena/issues/11) showed that the first version gave full credit to denied or hedged answers (*"It is not April 10th."*), to a list of the history's names on 30–39% of tasks, and failed about 1.5% of gold answers on themselves. On the 8,451 fact items of the cached evidence files (pinned revision), the current version:

| Reply | Scores 1.0 (before → now) |
|---|---|
| the gold answer itself, or lower-cased, or with a friendly opener or closer | 98.5% → 99.9–100% |
| the gold answer plus a few more names | 98.5% → 99.5% |
| the gold answer plus the latest evidence message quoted | 98.5% → 94.2% |
| *I don't remember. It is not this:* + gold | 98.5% → 0.1% |
| gold + *No, that is wrong, and I don't remember…* | 98.5% → 0.0% |
| *Either* (another answer) *or* gold. *I can't tell which.* | 95.2% → 2.9% |
| gold + *That is not it.* | 98.5% → 1.0% |
| *Not* + gold | 98.5% → 15.0% |
| (another answer); gold | 96.2% → 89.2% |
| every name and number of the evidence conversation, up to 100 words | 49.6% → 16.0% (23.2% in lower case) |

What it still can't do: tell an alternative from extra detail when nothing marks it (a bare *"W; R"*), catch a denial worded in a way the phrase lists don't cover, or stop a short list padded with function words. A word-level check cannot reliably separate a denial from ordinary text, which is why exact match is a sanity check: use the official judges for full-scale evaluation, for leaderboards, and whenever a reward will be optimized against. The judge-robustness miss also still holds: in *"a Caprese salad, a tomato basil pasta sauce and pesto"* only "Caprese" is a name, so a reply that gets the other two dishes wrong still passes.

## Judges

The judge prompts are copied **verbatim** from the reference implementation (`questions/evidence/generation/AnsweringEvaluation.scala`). Each category uses the same evaluator the paper does:

| Category | Reference evaluator | Class | Judge sees |
|---|---|---|---|
| `user_facts` (1 evidence) | `UserFactsAnsweringEvaluation` (single) | `UserFactsSingleJudge` | question, evidence message, gold answer, response |
| `user_facts` (2+ evidence) | `UserFactsAnsweringEvaluation` (multi) | `UserFactsMultiJudge` | question, numbered evidence messages, gold answer, response |
| `assistant_facts`, `changing_facts` | `DefaultAnsweringEvaluation` | `ConvoMemJudge` | question, gold answer, response |
| `abstention` | `AbstentionAnsweringEvaluation` | `AbstentionJudge` | question, response (a refusal or "I don't know" is RIGHT) |
| `preferences`, `implicit_connections` | `RubricBasedAnsweringEvaluation` | `RubricAnswerJudge` | question, rubric, response (must satisfy **all** criteria) |

**Verdict parsing** follows the reference: a reply containing only RIGHT → pass; WRONG, or both RIGHT and WRONG → fail; neither → **raise**. Raising rather than returning 0.0 means a broken judge shows up as an error instead of being recorded as a model mistake.

The judge endpoint defaults to verifiers' `JudgeConfig` (Prime Inference, key from `PRIME_API_KEY`). The paper used GPT-4o-mini and Gemini Flash during data validation. Pick a judge and keep it fixed when comparing runs, and check how far you can trust it with the [judge robustness checker](../quality/judge-robustness.md).

## Metrics (recorded in `tools` mode only)

| Name | Meaning |
|---|---|
| `memory_tool_calls` | Number of memory tool calls in the rollout |
| `evidence_recall` | Fraction of evidence conversations returned by at least one `memory_search` or `memory_read_conversation` call |
| `conversations_retrieved` | Distinct conversations the agent retrieved |

These are **metrics, not rewards**, so they're logged for analysis and never trained on. Rewarding recall directly would encourage the agent to dump the whole history. To experiment with it as a shaping signal, see [plugged rewards](../reference/architecture.md#plugging-extra-rewards).
