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


# --- issue #11: denied, hedged or retracted answers ---------------------------------------


@pytest.mark.parametrize(
    "reply",
    [
        "Either October fifth or April 10th.",  # the old value spelled out, past the number guard
        "It is not April 10th.",
        "April 10th? No, I don't think so. I don't remember.",
        f"I don't remember. It is not this: {GOLD}",
        f"{GOLD} No, that is wrong, and I don't remember the right answer.",
        f"{GOLD} That is not it.",
        "April 10th? No.",
        "April 10th. That's not right.",
        "April 10th. Or October.",
        "Maybe April 10th.",
        f"Not {GOLD}",
    ],
)
def test_denials_and_hedges_score_zero(reply):
    assert exact_match(reply, GOLD, Q, "changing_facts", EVIDENCE) == 0.0


@pytest.mark.parametrize(
    "reply",
    [
        "April 10th next year. Don't forget to update your calendar!",
        "Certainly! Based on what you told me, it's now April 10th next year.",
        "The National concert is scheduled for **April 10th (next year)**.",
    ],
)
def test_plain_answers_with_friendly_extras_still_score(reply):
    assert exact_match(reply, GOLD, Q, "changing_facts", EVIDENCE) == 1.0


def test_negation_the_gold_answer_has_itself_is_allowed():
    q = "Am I still allergic to peanuts?"
    gold = "No, you are not allergic to Brazil nuts anymore, only to peanuts."
    assert exact_match("You're not allergic to Brazil nuts anymore.", gold, q, "user_facts") == 1.0


# --- issue #11: candidate lists -------------------------------------------------------------

LQ = "What was that candidate's name?"
LGOLD = "The software engineer candidate's name was Liam Petrov."


@pytest.mark.parametrize(
    "reply",
    [
        "Liam Petrov Sarah Acme Boston 12 2019 Jordan Maya Google",
        "Sarah\nJordan\nLiam Petrov\nMaya\nAcme",  # one per line: line starts still count
        "Sarah; Jordan; Liam Petrov; Maya",
        "sarah jordan liam petrov maya acme boston",  # lower case: no names to count
        "Liam Petrov, Acme, Boston",
    ],
)
def test_candidate_lists_score_zero(reply):
    assert exact_match(reply, LGOLD, LQ, "user_facts") == 0.0


@pytest.mark.parametrize(
    "reply",
    ["Liam Petrov.", "His name was Liam Petrov.", "Liam Petrov, from Acme Corp in Boston."],
)
def test_answers_naming_a_few_more_things_still_score(reply):
    assert exact_match(reply, LGOLD, LQ, "user_facts") == 1.0


def test_i_dont_know_is_not_a_name_match():
    q = "Which carrier did I switch to?"
    gold = "You said I've switched to T-Mobile."
    assert exact_match("I don't know.", gold, q, "user_facts") == 0.0
    assert exact_match("T-Mobile.", gold, q, "user_facts") == 1.0


# --- issue #11: the answer and the reply read the same way ----------------------------------


@pytest.mark.parametrize(
    ("question", "gold", "reply", "score"),
    [
        ("Which flight?", "United Airlines, XY123456.", "United Airlines, XY123456.", 1.0),
        ("Which flight?", "United Airlines, XY123456.", "United Airlines, XY 123456.", 1.0),
        ("Whose talk?", "You suggested a talk by Brené Brown.", "Brené Brown.", 1.0),
        ("Whose talk?", "You suggested a talk by Brené Brown.", "Brene Brown.", 1.0),
        ("Whose talk?", "You suggested a talk by Brené Brown.", "Bren Brown.", 0.0),
        ("My Wi-Fi password?", "It is 'Pixel&Tomatoes22!'.", "It is 'Pixel&Tomatoes22!'.", 1.0),
        ("My Wi-Fi password?", "It is 'Pixel&Tomatoes22!'.", "It is 'Banana Tomatoes 22'.", 0.0),
        ("When is my alarm?", "Your alarm is set for 7 AM.", "7 a.m.", 1.0),
        ("When is my alarm?", "Your alarm is set for 7 AM.", "7 PM.", 0.0),
        ("Which headphones?", "You bought the Sony WH-1000XM4.", "Sony WH-1000XM4", 1.0),
        ("Which channel?", "I recommended 3Blue1Brown.", "3Blue1Brown", 1.0),
        ("What's my budget?", "Your budget is $2,100 for the trip.", "$2,100", 1.0),
        ("What's my budget?", "Your budget is $2,100 for the trip.", "$2,000", 0.0),
    ],
)
def test_answer_and_reply_are_read_the_same_way(question, gold, reply, score):
    assert exact_match(gold, gold, question, "user_facts") == 1.0
    assert exact_match(reply, gold, question, "user_facts") == score


def test_numbers_match_only_numbers():
    from convomem_arena.text import present

    assert present(["2"], "$2,100") == []
    assert present(["2100"], "$2,100") == ["2100"]


def test_hyphenated_and_possessive_names_the_question_holds_are_not_required_again():
    from convomem_arena.text import specifics

    assert specifics("Maya's Wi-Fi is fast.", "What did Maya's Wi-Fi do?") == []
    assert specifics("You loved 'Atomic Habits' by James Clear.") == [
        "atomic",
        "habits",
        "james",
        "clear",
    ]


# --- doubt with "can't", a denial before the answer, long answers without names -------------


@pytest.mark.parametrize(
    "reply",
    [
        "I can't remember. April 10th next year.",
        "I can't tell. April 10th next year.",
        "No idea. April 10th next year.",
        "It is not this. April 10th next year.",  # the denial sits in a sentence of its own
        "Either this or that. April 10th next year.",
    ],
)
def test_doubt_or_denial_before_the_answer_scores_zero(reply):
    assert exact_match(reply, GOLD, Q, "changing_facts", EVIDENCE) == 0.0


@pytest.mark.parametrize(
    ("question", "reply"),
    [
        ("I can't recall the exact day. When is The National concert now?", None),
        ("I do not recall the exact day. When is The National concert now?", None),
        (
            "I can't recall the exact day. When is The National concert now?",
            "I cannot recall the exact day either. " + GOLD,
        ),
        (
            "I can't recall the exact day. When is The National concert now?",
            "I can't recall the exact day, but " + GOLD[0].lower() + GOLD[1:],
        ),
    ],
)
def test_not_remembering_the_question_voices_may_be_echoed(question, reply):
    reply = reply or question + " " + GOLD
    assert exact_match(reply, GOLD, question, "changing_facts", EVIDENCE) == 1.0
    assert exact_match("I can't recall. " + GOLD, GOLD, Q, "changing_facts", EVIDENCE) == 0.0


def test_a_hedge_word_the_question_uses_still_scores_zero():
    q = "Maybe you remember my go-to spot for dinner?"
    gold = "Your go-to spot is Siam Spice."
    assert exact_match(gold, gold, q, "user_facts") == 1.0
    assert exact_match("Maybe Siam Spice.", gold, q, "user_facts") == 0.0


def test_a_denial_the_question_has_may_be_echoed():
    q = "Which city did I say I would not move to?"
    reply = "You said there is a city you would not move to. It is Boston."
    assert exact_match(reply, "Boston.", q, "user_facts") == 1.0
    assert exact_match(reply, "Boston.", "Which city did I mention?", "user_facts") == 0.0
    # an "either ... or" in the question doesn't excuse a "not"
    q = "Did I say Boston or Denver, either one?"
    assert exact_match("It is not this. It is Boston.", "Boston.", q, "user_facts") == 0.0


@pytest.mark.parametrize(
    "reply",
    [
        "Is it not this? April 10th next year.",
        "Not October, right? April 10th next year.",
    ],
)
def test_a_denial_asked_as_a_question_scores_zero(reply):
    assert exact_match(reply, GOLD, Q, "changing_facts", EVIDENCE) == 0.0


def test_a_rejecting_sentence_with_isnt_scores_zero():
    assert exact_match("Liam Petrov. That isn't it.", LGOLD, LQ, "user_facts") == 0.0
    assert exact_match("Liam Petrov. That wasn't it.", LGOLD, LQ, "user_facts") == 0.0
    assert exact_match("Liam Petrov. That was not it.", LGOLD, LQ, "user_facts") == 0.0
    assert exact_match("Liam Petrov. That's right.", LGOLD, LQ, "user_facts") == 1.0


@pytest.mark.parametrize(
    "reply",
    [
        "No problem! April 10th next year.",
        "Not a problem! April 10th next year.",
        "Not to worry! April 10th next year.",
        "Sure, here it is: April 10th next year.",
        "Either way, here is what you told me. April 10th next year.",
        "From what you told me, or at least how I remember it. April 10th next year.",
        "Do you mean the concert or the tour? April 10th next year.",  # a question asked back
    ],
)
def test_friendly_openers_still_score(reply):
    assert exact_match(reply, GOLD, Q, "changing_facts", EVIDENCE) == 1.0


PQ = "How should I plan my Saturday morning?"
PGOLD = (
    "Have breakfast at the small family restaurant. Walk through the quiet garden after that. "
    "Browse the old bookstore before lunch."
)


@pytest.mark.parametrize(
    "reply",
    [
        "Not " + PGOLD,
        "Either have breakfast at the small family restaurant or skip it. "
        + PGOLD.split(". ", 1)[1],
    ],
)
def test_denials_of_a_long_answer_without_names_score_zero(reply):
    assert exact_match(PGOLD, PGOLD, PQ, "user_facts") == 1.0
    assert exact_match(reply, PGOLD, PQ, "user_facts") == 0.0


def test_a_long_answer_without_names_restated_still_scores():
    reply = (
        "Have breakfast at the small family restaurant, then walk through the quiet garden "
        "and browse the old bookstore before lunch."
    )
    assert exact_match(reply, PGOLD, PQ, "user_facts") == 1.0


def test_a_one_sentence_answer_restated_over_several_sentences_still_scores():
    gold = (
        "Have breakfast at the small family restaurant, walk through the quiet garden, "
        "and browse the old bookstore before lunch."
    )
    reply = (
        "Have breakfast at the small family restaurant. Then walk through the quiet garden. "
        "Browse the old bookstore before lunch, but do not rush."
    )
    assert exact_match(reply, gold, PQ, "user_facts") == 1.0
