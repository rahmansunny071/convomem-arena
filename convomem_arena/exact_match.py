"""Deterministic scoring for the three fact categories, as an alternative to the judge.

ConvoMem's gold answers are full sentences ("The concert has been postponed to April
10th of next year."), so a literal string comparison almost never matches. Instead, a
reply matches when it contains the answer's **details**: its names and numbers that the
question doesn't already contain ("april", "10"). Answers without names or numbers fall
back to their content words.

Two guards keep the score honest as a training reward:

- **No dumping.** A reply far longer than the answer scores 0, so listing everything
  in the history can't collect the details by brute force.
- **No stale numbers** (`changing_facts`). A reply that also states a number from an
  earlier evidence message, one the latest message and the answer no longer contain,
  scores 0: "October 5th or April 10th" hedges instead of tracking the change. Only
  numbers count, because replies often name the old value as history ("postponed from
  the original October date"), which the judges rightly accept.

It costs nothing, needs no judge endpoint and never varies between runs, but it is
stricter than the official judges on paraphrase. Use the judges to compare with the
ConvoMem paper; use this where a cheap, stable signal matters more.
"""

from __future__ import annotations

from convomem_arena.text import (
    content_words,
    coverage,
    is_number,
    key_terms,
    present,
    specifics,
    words,
)

FACT_CATEGORIES = ("user_facts", "assistant_facts", "changing_facts")

KEY_TERM_THRESHOLD = 0.6
"""Share of an answer's content words a reply needs when the answer has no details."""

MAX_LENGTH_FACTOR = 5
MIN_LENGTH_ALLOWANCE = 100
"""A reply may use up to max(100, 5 × the answer's length) words before it counts as
dumping. Correct replies often cite where they found the answer; dumps run to hundreds."""


def answer_details(answer: str, question: str) -> list[str]:
    """The answer's names and numbers that the question doesn't already contain."""
    return specifics(answer, question)


def stale_details(answer: str, question: str, evidence_messages: list[str]) -> list[str]:
    """Numbers from earlier evidence that the latest evidence and the answer no longer
    contain: the superseded values of a changing fact."""
    if len(evidence_messages) < 2:
        return []
    keep = set(specifics(evidence_messages[-1])) | set(specifics(answer)) | set(words(question))
    earlier = specifics(" ".join(evidence_messages[:-1]))
    return [d for d in earlier if d not in keep and is_number(d)]


def exact_match(
    response: str,
    answer: str,
    question: str,
    category: str,
    evidence_messages: list[str] | None = None,
) -> float:
    """1.0 when `response` states the answer's details (see the module docstring), else 0.0."""
    if category not in FACT_CATEGORIES or not response.strip():
        return 0.0
    limit = max(MIN_LENGTH_ALLOWANCE, MAX_LENGTH_FACTOR * len(words(answer)))
    if len(words(response)) > limit:
        return 0.0
    details = answer_details(answer, question)
    if details:
        if len(present(details, response)) < len(details):
            return 0.0
    else:
        terms = key_terms(answer, question) or content_words(answer)
        if coverage(terms, response) < KEY_TERM_THRESHOLD:
            return 0.0
    if category == "changing_facts" and present(
        stale_details(answer, question, evidence_messages or []), response
    ):
        return 0.0
    return 1.0
