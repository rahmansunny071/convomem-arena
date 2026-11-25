"""Deterministic scoring for the three fact categories, as an alternative to the judge.

ConvoMem's gold answers are full sentences ("The concert has been postponed to April
10th of next year."), so a literal string comparison almost never matches. Instead, a
reply matches when it contains the answer's **details**: its names and numbers that the
question doesn't already contain ("april", "10"). Answers without names or numbers fall
back to their content words.

Four guards keep the score honest as a training reward:

- **No dumping.** A reply far longer than the answer scores 0, so listing everything
  in the history can't collect the details by brute force.
- **No candidate lists.** A reply offering many names or numbers that neither the answer
  nor the question contains scores 0 (more than 8, or 3 or more making up over half of
  its words), so a short list of the history's names can't hit the answer by chance.
- **No hedging or denial.** A reply scores 0 when it voices doubt the answer doesn't
  ("I don't remember", "I can't tell", "maybe", "wrong"; not remembering that the question
  voices may be echoed), when the sentences stating the answer's details negate or offer
  alternatives ("not", "no", "or", "either", "n't") more often than the answer itself does,
  when a lead-in before them denies or offers an alternative ("It is not this.",
  "Either ... or ...") more often than the question does, or when a sentence of its own
  rejects or adds an alternative ("Nope.", "That's not right.", "Or October.").
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

import re

from convomem_arena.text import (
    STOP,
    content_words,
    coverage,
    fold,
    is_number,
    key_terms,
    numbers,
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

MAX_EXTRA_DETAILS = 8
LIST_MIN_EXTRA = 3
LIST_MAX_SHARE = 0.5
DENSE_MIN_EXTRA = 2
DENSE_SHARE = 0.75
BARE_MIN_EXTRA = 3
BARE_STOP_SHARE = 0.15
"""A reply is a list of candidates rather than an answer when it holds more than 8 names or
numbers the answer and question lack, or 3 or more of them making up over half of its
words, or 2 or more in a reply that is at least 75% names and numbers ("Liam Petrov, Acme,
Boston"), or 3 or more new content words with almost no function words, in any case
("liam petrov sarah acme boston"). A sentence around the names ("Liam Petrov, from Acme
Corp in Boston.") passes."""

_NOT_RECALLING = re.compile(
    r"\b(?:(?:do|did|can|could)(?:n't| not)|can't|cannot|i'?m not|not)\s+"
    r"(?:know|remember|recall|tell|think|sure|certain|be sure)\b"
)
_HEDGE = re.compile(
    r"\b(?:unsure|uncertain|maybe|perhaps|possibly|probably|guess|guessing|wrong|incorrect)\b"
    r"|\bno idea\b"
)
_NEGATION = re.compile(r"\b(?:not|no|never|nor|or|either|neither)\b|n't\b")
_LEAD_DENIAL = re.compile(r"\b(?:not(?! a problem\b| to worry\b)|nor|neither)\b")
_LEAD_EITHER, _LEAD_OR = re.compile(r"\beither\b"), re.compile(r"\bor\b")
_REJECTION = re.compile(
    r"^(?:no|nope|nah|wrong|incorrect)\b\W*(?:$|,)"
    r"|^(?:that|this|it)(?:(?:'s| is|s| was)? not| isn't| wasn't) "
    r"(?:it|right|correct|true|the answer)\b"
    r"|^not (?:it|right|correct|true|quite)\b"
    r"|^or\b"
)
"""Doubt the gold answer doesn't voice (not remembering, unless the question says the same;
a hedge word, always); negation or alternatives; in a lead-in before the answer, a denial
("not", "nor", "neither"; "Not a problem!" and "Not to worry!" are fine) or a sentence with
"either ... or", beyond what the question has, but not a lone "or" ("or at least") or
"Either way"; a sentence that rejects."""


def _recall_key(phrase: str) -> str:
    """'can't recall', 'cannot recall' and 'can not recall' read alike."""
    phrase = re.sub(r"\bcan't\b|\bcannot\b", "can not", phrase)
    return re.sub(r"n't\b", " not", phrase)


def _lead_denials(sentences: list[str]) -> tuple[int, int]:
    """Denials, and the words of "either ... or" sentences, in `sentences`."""
    denials = alternatives = 0
    for sentence in sentences:
        denials += len(_LEAD_DENIAL.findall(sentence))
        if _LEAD_EITHER.search(sentence) and _LEAD_OR.search(sentence):
            alternatives += len(_LEAD_EITHER.findall(sentence)) + len(_LEAD_OR.findall(sentence))
    return denials, alternatives


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


def _plain(text: str) -> str:
    """Lowercased and folded, curly apostrophes made straight, for the phrase checks."""
    return fold(text).lower().replace("\u2019", "'")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", _plain(text)) if s.strip()]


def extra_details(response: str, answer: str, question: str) -> list[str]:
    """Names and numbers in `response` that neither `answer` nor `question` contains,
    counting those that open a short line or list item."""
    known = set(words(answer)) | numbers(answer) | set(words(question)) | numbers(question)
    return [d for d in specifics(response, short_starts=True) if d not in known]


def is_candidate_list(response: str, answer: str, question: str) -> bool:
    extra = extra_details(response, answer, question)
    size = len(words(response))
    if len(extra) > MAX_EXTRA_DETAILS:
        return True
    if len(extra) >= LIST_MIN_EXTRA and len(extra) > LIST_MAX_SHARE * size:
        return True
    named = sum(len(words(d)) for d in specifics(response, short_starts=True))
    if len(extra) >= DENSE_MIN_EXTRA and named >= DENSE_SHARE * size:
        return True
    # a list in lower case has no capitalised names to count, but no sentence either
    known = set(words(answer)) | set(words(question))
    new_terms = [w for w in content_words(response) if w not in known]
    function_words = sum(w in STOP for w in words(response))
    return len(new_terms) >= BARE_MIN_EXTRA and function_words < BARE_STOP_SHARE * size


def hedges(
    response: str, answer: str, details: list[str], terms: list[str], question: str = ""
) -> bool:
    """True when `response` doubts, denies or hedges what `answer` states plainly."""
    gold, reply, asked = _plain(answer), _plain(response), _plain(question)
    if _HEDGE.search(reply) and not _HEDGE.search(gold):
        return True
    if not _NOT_RECALLING.search(gold):
        # not remembering that the user voiced in the question ("I can't recall the day")
        # may be echoed; the echoed words then don't count as a denial either
        echoed = {_recall_key(m.group()) for m in _NOT_RECALLING.finditer(asked)}
        for m in _NOT_RECALLING.finditer(reply):
            if _recall_key(m.group()) not in echoed:
                return True
        reply = _NOT_RECALLING.sub(" ", reply)
        asked = _NOT_RECALLING.sub(" ", asked)
    gold_rejects = any(_REJECTION.search(s) for s in _sentences(answer))
    if not gold_rejects and any(_REJECTION.search(s) for s in _sentences(reply)):
        return True
    # negation or alternatives in the sentences stating the answer, beyond what the answer
    # has itself, and a denial or an "either ... or" in a lead-in before the first of them
    # ("Not: <answer>"), beyond what the question has (it may be echoed)
    allowed = len(_NEGATION.findall(gold))
    # an answer without names is stated sentence by sentence: half the key terms of one of
    # its sentences, as a long answer is often not restated in a single sentence
    wanted = set(terms)
    parts = []
    for sentence in _sentences(answer):
        part = [w for w in content_words(sentence) if w in wanted]
        if part:
            parts.append(part)
    stated, first = 0, None
    sentences = _sentences(reply)
    for i, sentence in enumerate(sentences):
        if details:
            states = bool(present(details, sentence))
        else:
            states = any(coverage(part, sentence) >= 0.5 for part in parts)
        if states:
            first = i if first is None else first
            stated += len(_NEGATION.findall(sentence))
    # without a sentence stating the answer there is no lead-in to read
    lead_in = sentences[:first] if first is not None else []
    denied = sum(
        max(0, here - there)
        for here, there in zip(_lead_denials(lead_in), _lead_denials(_sentences(asked)))
    )
    return stated + denied > allowed


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
    if is_candidate_list(response, answer, question):
        return 0.0
    details = answer_details(answer, question)
    terms: list[str] = []
    if details:
        if len(present(details, response)) < len(details):
            return 0.0
    else:
        terms = key_terms(answer, question) or content_words(answer)
        if coverage(terms, response) < KEY_TERM_THRESHOLD:
            return 0.0
    if hedges(response, answer, details, terms, question):
        return 0.0
    if category == "changing_facts" and present(
        stale_details(answer, question, evidence_messages or []), response
    ):
        return 0.0
    return 1.0
