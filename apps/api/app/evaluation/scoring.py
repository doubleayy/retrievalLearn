"""The rubric: graded relevance judgments in, a score out of 5 out.

Deliberately simple arithmetic rather than a standard IR metric. nDCG is the
right tool for comparing two rankers on the same task, but it is opaque to
anyone who has not met it before, and this is a teaching app. Three named
components that visibly add up to five can be argued with, which is the point.

    top_hit      0-2   was the first thing you were shown the right thing?
    coverage     0-2   how much of the correct answer surfaced at all?
    cleanliness  0-1   how much of the page was wrong, or actively misleading?

Every mode is truncated to the same K before scoring, so a mode that returns 25
rows gets no advantage over one that returns 8.
"""

from __future__ import annotations

from typing import Any

K = 8
"""Results per mode considered by the rubric. Matches the app's default limit."""

NOISE_WINDOW = 5
"""Cleanliness only looks at the top of the page, because nobody scrolls."""

# Relevance grades used by the suite.
ANSWERS = 3   # this *is* the answer, or states it outright
EVIDENCE = 2  # genuine supporting material, but does not answer on its own
TOPICAL = 1   # on-topic and useless

_TOP_HIT_POINTS = {ANSWERS: 2.0, EVIDENCE: 1.2, TOPICAL: 0.5, 0: 0.0}
_TRAP_PENALTY = 0.30
_MISS_PENALTY = 0.08

RUBRIC: dict[str, Any] = {
    "k": K,
    "noise_window": NOISE_WINDOW,
    "grades": [
        {"grade": ANSWERS, "name": "Answers", "meaning": "This is the answer, or states it outright."},
        {"grade": EVIDENCE, "name": "Evidence", "meaning": "Real supporting material that does not answer on its own."},
        {"grade": TOPICAL, "name": "Topical", "meaning": "On-topic and useless."},
        {"grade": 0, "name": "Irrelevant", "meaning": "Not judged relevant to this question."},
        {"grade": -1, "name": "Trap", "meaning": "Wrong, and tempting: authored to be retrieved by a specific failure mode."},
    ],
    "components": [
        {
            "id": "top_hit",
            "name": "Top hit",
            "max": 2.0,
            "how": "The grade of rank 1, scored 3→2.0, 2→1.2, 1→0.5, irrelevant or trap→0.",
            "why": "Most people read the first result and stop. A mode that buries the "
                   "right answer at rank 6 has not helped them.",
        },
        {
            "id": "coverage",
            "name": "Coverage",
            "max": 2.0,
            "how": f"2.0 x (grade-3 items retrieved / min(grade-3 items that exist, {K})).",
            "why": "Recall@K, capped so that a question with 27 correct answers is not "
                   "unscoreable in an 8-row page.",
        },
        {
            "id": "cleanliness",
            "name": "Cleanliness",
            "max": 1.0,
            "how": f"1.0 - {_TRAP_PENALTY} per trap - {_MISS_PENALTY} per irrelevant "
                   f"result, counted over the top {NOISE_WINDOW}. Floored at 0.",
            "why": "Precision, weighted so a planted trap costs roughly four times what "
                   "ordinary noise costs. Being confidently wrong is worse than being vague.",
        },
    ],
    "empty_rule": "A mode that returns nothing scores 0. Silence is not precision.",
    "rounding": "Components are summed, then rounded to the nearest half point.",
}


def grade_for(candidates: set[str], judgments: dict[str, int], traps: dict[str, str]) -> tuple[int, str]:
    """Best grade any of a result's candidate ids earns. -1 marks a trap."""
    for cid in candidates:
        if cid in traps:
            return -1, traps[cid]
    best = 0
    for cid in candidates:
        best = max(best, judgments.get(cid, 0))
    return best, ""


def score(graded: list[dict[str, Any]], judgments: dict[str, int], traps: dict[str, str]) -> dict[str, Any]:
    """Score one mode's already-graded top-K results.

    `graded` is rank-ordered and already truncated to K; each entry carries the
    `grade` and the set of `credited` ids that earned it.
    """
    if not graded:
        return {
            "total": 0.0,
            "top_hit": 0.0,
            "coverage": 0.0,
            "cleanliness": 0.0,
            "retrieved": 0,
            "answers_found": 0,
            "answers_possible": min(len([g for g in judgments.values() if g == ANSWERS]), K),
            "traps_hit": 0,
            "irrelevant_in_window": 0,
            "first_answer_rank": None,
            "empty": True,
        }

    top_grade = graded[0]["grade"]
    top_hit = _TOP_HIT_POINTS.get(max(top_grade, 0), 0.0)

    answer_ids = {doc_id for doc_id, g in judgments.items() if g == ANSWERS}
    found: set[str] = set()
    for entry in graded:
        found |= {cid for cid in entry["credited"] if cid in answer_ids}
    possible = min(len(answer_ids), K)
    coverage = 2.0 * (len(found) / possible) if possible else 0.0
    coverage = min(coverage, 2.0)

    window = graded[:NOISE_WINDOW]
    traps_hit = sum(1 for e in window if e["grade"] == -1)
    irrelevant = sum(1 for e in window if e["grade"] == 0)
    cleanliness = max(0.0, 1.0 - _TRAP_PENALTY * traps_hit - _MISS_PENALTY * irrelevant)

    first_answer = next((e["rank"] for e in graded if e["grade"] == ANSWERS), None)
    total = _round_half(top_hit + coverage + cleanliness)

    return {
        "total": total,
        "top_hit": round(top_hit, 2),
        "coverage": round(coverage, 2),
        "cleanliness": round(cleanliness, 2),
        "retrieved": len(graded),
        "answers_found": len(found),
        "answers_possible": possible,
        "traps_hit": sum(1 for e in graded if e["grade"] == -1),
        "irrelevant_in_window": irrelevant,
        "first_answer_rank": first_answer,
        "empty": False,
    }


def _round_half(value: float) -> float:
    return max(0.0, min(5.0, round(value * 2) / 2))


def verdict(components: dict[str, Any], graded: list[dict[str, Any]], mode: str) -> str:
    """A one-line, purely mechanical reading of the numbers.

    Kept separate from the authored commentary in the suite so that the two can
    disagree: if the sentence generated from the run contradicts the lesson the
    test was written to teach, the test is wrong.
    """
    if components["empty"]:
        return "Returned nothing at all."

    total = components["total"]
    first = graded[0]
    parts: list[str] = []

    if first["grade"] == -1:
        parts.append(f"Rank 1 is a planted trap ({first['title']}).")
    elif first["grade"] == ANSWERS:
        parts.append(f"Rank 1 is correct ({first['title']}).")
    elif first["grade"] == EVIDENCE:
        parts.append(f"Rank 1 is supporting evidence, not an answer ({first['title']}).")
    elif first["grade"] == TOPICAL:
        parts.append(f"Rank 1 is on-topic but does not answer ({first['title']}).")
    else:
        parts.append(f"Rank 1 is unrelated ({first['title']}).")

    found, possible = components["answers_found"], components["answers_possible"]
    parts.append(f"Found {found} of {possible} correct answers in the top {K}.")

    if components["traps_hit"]:
        n = components["traps_hit"]
        parts.append(f"{n} trap{'s' if n > 1 else ''} retrieved.")

    if total >= 4.5:
        parts.append("This is what a solved question looks like.")
    elif total <= 1.0:
        parts.append("Effectively no help on this question.")
    return " ".join(parts)
