"""Offline tests for the deterministic fact scorer and how the task uses it."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import convomem_arena.taskset as taskset_module
from convomem_arena.exact_match import exact_match, stale_details
from convomem_arena.models import ConvoMemData
from convomem_arena.taskset import ConvoMemTask, ConvoMemTaskConfig

Q = "What is the date for The National concert?"
GOLD = "The concert has been postponed to April 10th of next year."
EVIDENCE = [
    "They're playing here in SF on October 5th. It's going to be amazing.",
    "The entire tour is being postponed. My new show date is April 10th next year.",
]


@pytest.mark.parametrize(
    ("reply", "score"),
    [
        ("April 10th next year.", 1.0),
        ("It was moved to April 10.", 1.0),
        ("Postponed from the original October date to April 10th.", 1.0),  # old month as history
        ("October 5th.", 0.0),  # the superseded value
        ("Either October 5th or April 10th.", 0.0),  # hedging between old and new
        ("The concert was postponed.", 0.0),  # no detail
        ("", 0.0),
    ],
)
def test_changing_fact(reply, score):
    assert exact_match(reply, GOLD, Q, "changing_facts", EVIDENCE) == score


def test_stale_details_are_superseded_numbers_only():
    assert stale_details(GOLD, Q, EVIDENCE) == ["5"]
    assert stale_details(GOLD, Q, EVIDENCE[-1:]) == []


def test_names_must_all_appear():
    q = "Which influencer did you recommend I follow?"
    gold = "Shreyas Doshi"
    assert (
        exact_match("You should follow **Shreyas Doshi** on Twitter.", gold, q, "assistant_facts")
        == 1.0
    )
    assert exact_match("You should follow Lenny Rachitsky.", gold, q, "assistant_facts") == 0.0


def test_answer_without_names_falls_back_to_content_words():
    q = "What did I say I was learning?"
    gold = "You said you were learning watercolor painting."
    assert exact_match("Watercolor painting.", gold, q, "user_facts") == 1.0
    assert exact_match("Pottery.", gold, q, "user_facts") == 0.0


def test_dumping_the_history_scores_zero():
    dump = "April 10th. " + "Here is everything else I remember about you. " * 30
    assert exact_match(dump, GOLD, Q, "changing_facts", EVIDENCE) == 0.0


def test_only_fact_categories_are_scored():
    assert exact_match("I don't know.", GOLD, Q, "abstention") == 0.0
    assert exact_match("April 10th", GOLD, Q, "preferences") == 0.0


def _task(category: str, fact_scoring: str) -> ConvoMemTask:
    data = ConvoMemData(
        prompt="p",
        question=Q,
        answer=GOLD,
        category=category,
        evidence_count=2,
        context_size=2,
        evidence_messages=EVIDENCE,
    )
    return ConvoMemTask(data, ConvoMemTaskConfig(fact_scoring=fact_scoring))


def test_exact_match_reward_skips_the_judge(monkeypatch):
    def no_judge(*args, **kwargs):
        raise AssertionError("the judge must not be called")

    monkeypatch.setattr(taskset_module, "judge_for", no_judge)
    task = _task("changing_facts", "exact_match")
    good = SimpleNamespace(last_reply="April 10th next year.")
    bad = SimpleNamespace(last_reply="October 5th.")
    assert asyncio.run(task.correct(good)) == 1.0
    assert asyncio.run(task.correct(bad)) == 0.0


def test_default_still_uses_the_judge(monkeypatch):
    called = []

    def fake_judge(*args, **kwargs):
        called.append(args)
        raise RuntimeError("judge reached")

    monkeypatch.setattr(taskset_module, "judge_for", fake_judge)
    assert ConvoMemTaskConfig().fact_scoring == "judge"
    with pytest.raises(RuntimeError, match="judge reached"):
        asyncio.run(_task("changing_facts", "judge").correct(SimpleNamespace(last_reply="x")))
    # non-fact categories use their judge even when fact scoring is exact match
    with pytest.raises(RuntimeError, match="judge reached"):
        asyncio.run(_task("abstention", "exact_match").correct(SimpleNamespace(last_reply="x")))
    assert len(called) == 2


def test_metric_records_exact_match_for_fact_categories_only():
    reply = SimpleNamespace(last_reply="April 10th next year.")
    assert asyncio.run(_task("changing_facts", "judge").deterministic(reply)) == {
        "exact_match": 1.0
    }
    assert asyncio.run(_task("abstention", "judge").deterministic(reply)) == {}
