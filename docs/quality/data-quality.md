---
title: "Data quality"
description: "Deterministic checks that audit ConvoMem items for structural errors, grounding problems and filler conflicts."
---

# Data quality

`python -m convomem_arena.data_check --out outputs/data-check/run1` audits a sample of items with deterministic checks (no model calls). It samples a few items from each of several persona files in every category and evidence-count folder, so the sample is spread across personas.

| Check | Severity | Flags an item when |
|---|---|---|
| `empty_field` | error | the question or answer is empty |
| `evidence_count_mismatch` | error | the number of evidence messages differs from the folder's count |
| `flagged_conversation_count` | error | conversations marked `containsEvidence` differ from that count |
| `evidence_not_in_conversations` | error | an evidence message has no close match (similarity < 0.85) in any of its conversations |
| `evidence_speaker_mismatch` | error | an evidence message's speaker differs from the conversation's |
| `evidence_reworded_in_conversation` | review | an evidence message appears only reworded (usually a changed lead-in; the fact is intact) |
| `wrong_evidence_speaker` | review | user facts are said by the assistant, or assistant facts by the user |
| `answer_restates_question` | review | the answer adds no content words beyond the question |
| `answer_name_not_in_evidence` | review | a name in the answer is in neither the evidence nor the question |
| `answer_number_not_in_evidence` | review | a number in the answer is not in the evidence (usually a computed total or average) |
| `latest_evidence_not_answer` | review | changing facts: an earlier evidence message matches the answer better than the last |
| `answer_terms_in_filler` | review | one filler message of the same persona holds the answer's details, including a name |
| `question_topic_in_filler` | review | abstention: one filler message holds most of the question's key words |
| `duplicate_question` | review | the same question appears in more than one sampled item |

An answer's "details" are its names (capitalised words that don't start a sentence) and numbers, list markers excluded: ConvoMem's gold answers are often written-out advice, so their other words rarely appear in the evidence, but their names and numbers should. Filler matches must co-occur in a single message and include a name, since numbers and scattered words recur by coincidence.

The [data card](data-card.md) summarises these findings with what ConvoMem's paper says about how the data was made.

**First results (2026-11-17, 368 items from 62 personas, filler checked for 25):** 290 items had no flags. Structural errors were rare (3 items: one implicit-connections item with two evidence messages in a one-evidence folder, one abstention item whose evidence matches its conversation at only 0.82). 11 items carried evidence only in reworded form, fact intact. Reading every review flag by hand: missing numbers were almost all computed totals and averages (user facts that test arithmetic over memory); one gold answer relied on world knowledge (a recommended city and museum) rather than the user's history; and filler held true conflicts in a few changing-facts items (the gold answer names Jessica as the new Head of Sales Ops while the same persona's filler names Helen Vance), which a random mix can place after the evidence. Other filler hits were harmless repeats of the same fact, or coincidences.

**error** flags are facts about the file. **review** flags are heuristic pointers, written with the item's text to `review.md` for a human to confirm or dismiss. Filler checks download each persona's filler file (about 5.6 MB); `--filler-personas` caps how many (default 25). Raise `--files-per-folder` and `--items-per-file` to audit more, up to the whole dataset.
