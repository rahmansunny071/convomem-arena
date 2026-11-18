"""Small, deterministic text helpers shared by the quality checkers."""

from __future__ import annotations

import re

_STOP_WORDS = (
    "the a an and or of to in on for with at by from is are was were be been being it its "
    "this that these those your you my our their his her they them there what which who "
    "whom when where how why should would could can will just also than then into about "
    "over not no yes did does do has have had i me we us he she as so if but"
)
STOP = frozenset(_STOP_WORDS.split())


def norm(text: str) -> str:
    """Lowercase, punctuation to spaces, whitespace collapsed."""
    return re.sub(r"\W+", " ", text.lower()).strip()


def words(text: str) -> list[str]:
    return norm(text).split()


def content_words(text: str) -> list[str]:
    """Distinct non-stopword tokens of three or more characters (or any number), in order."""
    out = [w for w in words(text) if w not in STOP and (len(w) >= 3 or w.isdigit())]
    return list(dict.fromkeys(out))


def key_terms(answer: str, question: str = "") -> list[str]:
    """Content words of `answer` that `question` doesn't already contain.

    Gold answers often restate the question ("Your go-to spot for a casual weeknight
    dinner is Siam Spice"); only the new words ("siam", "spice") carry the fact.
    """
    asked = set(words(question))
    return [w for w in content_words(answer) if w not in asked]


def numbers(text: str) -> set[str]:
    """Numbers in `text`, thousands separators removed ("$1,150" -> "1150")."""
    return {n.replace(",", "") for n in re.findall(r"\d+(?:[.,]\d+)*", text)}


def specifics(answer: str, question: str = "") -> list[str]:
    """The checkable details of an answer: numbers and names (capitalised words that
    don't start a sentence), minus anything the question already contains.

    Gold answers are often written-out advice ("Certainly. Based on your goals, …"),
    so most of their words never appear in the evidence; their names and numbers must.
    """
    # list markers (line-start "1." / "-" and inline "1)") aren't details
    answer = re.sub(r"(?m)^\s*(?:\d+[.)]|[-*•])\s+", "", answer)
    answer = re.sub(r"(?<![\w$.,])\d+\)\s", " ", answer)
    asked_words, asked_numbers = set(words(question)), numbers(question)
    found = [n for n in numbers(answer) if n not in asked_numbers]
    for m in re.finditer(r"[A-Za-z][A-Za-z'-]*", answer):
        token = m.group()
        before = answer[: m.start()].rstrip()
        sentence_start = not before or before[-1] in ".!?:\n*-•\"'(" or before.endswith("**")
        lowered = norm(token)
        if (
            token[0].isupper()
            and not sentence_start
            and lowered not in STOP
            and lowered not in asked_words
            and len(lowered) > 1
        ):
            found.append(lowered.split()[0])
    return list(dict.fromkeys(found))


def is_number(term: str) -> bool:
    return term[:1].isdigit()


def present(terms: list[str], text: str) -> list[str]:
    """The `terms` (words or numbers from `specifics`) that occur in `text`."""
    ws, ns = set(words(text)), numbers(text)
    return [t for t in terms if t in ns or t in ws]


def coverage(terms: list[str], text: str) -> float:
    """Share of `terms` that occur in `text` as whole words (0.0 when there are none)."""
    if not terms:
        return 0.0
    present = set(words(text))
    return sum(t in present for t in terms) / len(terms)
