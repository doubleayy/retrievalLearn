"""Run the fixed test suite against every retrieval mode and bake a report.

    python -m app.evaluation.runner                 # pinned plans, no API key needed
    python -m app.evaluation.runner --live-planner  # use the real Claude planner
    python -m app.evaluation.runner --check         # re-run and diff against the
                                                    # committed report, exit 1 on drift

The output is a single JSON file served verbatim from /api/eval. Nothing in
this module runs at request time: 12 questions x 5 modes is 60 retrievals and,
with a live planner, 12 model calls. Paying that per visitor would be absurd,
and a report that changes between two people looking at it is not a report.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from ..config import DATA_DIR, EMBED_MODEL, PLANNER_MODEL
from ..index import ArenaIndex, index
from ..retrievers import graphsearch, hybrid, keyword, semantic
from ..schemas import ExecutedStep, ResultItem
from ..stores.vectors import embed_query
from . import scoring
from .scoring import ANSWERS, EVIDENCE, K, TOPICAL
from .suite import FAMILIES, TEST_CASES

REPORT_PATH = DATA_DIR / "eval_report.json"

MODES = ["keyword", "semantic", "graph", "hybrid", "hybrid_ontology"]

MODE_LABELS = {
    "keyword": "Keyword",
    "semantic": "Semantic",
    "graph": "Graph",
    "hybrid": "Hybrid",
    "hybrid_ontology": "Hybrid + ontology",
}


# --- id normalisation -----------------------------------------------------


class Resolver:
    """Maps a result card back to the ids the judgments are written against.

    Most results carry a namespaced id already (`article:n13`, `player:kd`).
    Graph aggregations do not: a row like `{team: 'PHX', picks: 4}` is the
    correct answer to the pick-ledger question and has no document id at all.
    Rather than exclude those rows from scoring - which would silently punish
    the one mode capable of answering - projected rows are scanned for values
    that name a known entity, and credited for it.
    """

    def __init__(self, idx: ArenaIndex) -> None:
        assert idx.conn is not None
        self.by_value: dict[str, str] = {}
        for row in idx.conn.execute("SELECT id, name FROM players"):
            self.by_value[row["id"].lower()] = f"player:{row['id']}"
            self.by_value[row["name"].lower()] = f"player:{row['id']}"
        for row in idx.conn.execute("SELECT id, name, city FROM teams"):
            for value in (row["id"], row["name"], row["city"]):
                if value:
                    self.by_value.setdefault(value.lower(), f"team:{row['id']}")
        for row in idx.conn.execute("SELECT id FROM articles"):
            self.by_value[row["id"].lower()] = f"article:{row['id']}"

    def credited(self, item: ResultItem) -> set[str]:
        ids = {item.id}
        if item.kind != "path":
            return ids
        for value in (item.data.get("row") or {}).values():
            if isinstance(value, str):
                hit = self.by_value.get(value.strip().lower())
                if hit:
                    ids.add(hit)
        return ids


# --- running one cell -----------------------------------------------------


def run_mode(
    idx: ArenaIndex, mode: str, plan: dict[str, Any], question: str
) -> tuple[list[ExecutedStep], list[ResultItem], list[str], dict | None]:
    """Execute one mode exactly the way /api/search does."""
    if mode == "keyword":
        step, results, warn = keyword.run(idx, plan["keyword_query"], K)
        return [step], results, warn, None
    if mode == "semantic":
        steps, results, warn = semantic.run(idx, plan["semantic_query"], K)
        return steps, results, warn, None
    if mode == "graph":
        steps, results, warn, _ = graphsearch.run(idx, plan["cypher"], K, question=question)
        return steps, results, warn, None
    steps, results, fusion, trace, warn, _ = hybrid.run(
        idx,
        plan,
        K,
        use_ontology=(mode == "hybrid_ontology"),
        question=question,
        repair=None,
    )
    return steps, results, warn, {
        "fusion": fusion,
        "ontology_trace": trace.model_dump() if trace else None,
    }


def evaluate(idx: ArenaIndex, resolver: Resolver, case: dict[str, Any], mode: str) -> dict[str, Any]:
    plan = case["plan"]
    started = time.perf_counter()
    steps, results, warnings, extra = run_mode(idx, mode, plan, case["query"])
    elapsed = round((time.perf_counter() - started) * 1000, 1)

    judgments: dict[str, int] = case["judgments"]
    traps: dict[str, str] = case["traps"]

    graded: list[dict[str, Any]] = []
    for item in results[:K]:
        credited = resolver.credited(item)
        grade, trap_reason = scoring.grade_for(credited, judgments, traps)
        graded.append(
            {
                "rank": item.rank,
                "id": item.id,
                "kind": item.kind,
                "title": item.title,
                "snippet": _short(item.snippet),
                "score": item.score,
                "why": item.why,
                "grade": grade,
                "trap_reason": trap_reason,
                "credited": sorted(credited),
            }
        )

    components = scoring.score(graded, judgments, traps)
    return {
        "mode": mode,
        "score": components["total"],
        "components": components,
        "verdict": scoring.verdict(components, graded, mode),
        "commentary": case.get("commentary", {}).get(mode, ""),
        "results": graded,
        "steps": [_step(s) for s in steps],
        "warnings": warnings,
        "latency_ms": elapsed,
        "ontology_trace": (extra or {}).get("ontology_trace"),
        "fusion_legs": ((extra or {}).get("fusion") or {}).get("legs"),
    }


def _step(step: ExecutedStep) -> dict[str, Any]:
    return {
        "label": step.label,
        "language": step.language,
        "code": step.code,
        "engine": step.engine,
        "row_count": step.row_count,
        "latency_ms": step.latency_ms,
        "note": step.note,
        "error": step.error,
    }


def _short(text: str, limit: int = 180) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


# --- validation -----------------------------------------------------------


def validate(resolver: Resolver) -> list[str]:
    """Every judged id must name something real. A typo in a gold set is a
    silently deflated score, which is the worst kind of broken eval."""
    problems: list[str] = []
    known = set(resolver.by_value.values())
    for case in TEST_CASES:
        overlap = set(case["judgments"]) & set(case["traps"])
        if overlap:
            problems.append(f"{case['id']}: judged and trapped the same id: {sorted(overlap)}")
        for doc_id in list(case["judgments"]) + list(case["traps"]):
            if doc_id not in known:
                problems.append(f"{case['id']}: judgment references unknown id {doc_id!r}")
        if not any(g == ANSWERS for g in case["judgments"].values()):
            problems.append(f"{case['id']}: no grade-3 answers, coverage is unscoreable")
        for field in ("preamble", "what_good_looks_like", "headline", "family"):
            if not case.get(field):
                problems.append(f"{case['id']}: missing {field}")
        if case["family"] not in {f["id"] for f in FAMILIES}:
            problems.append(f"{case['id']}: unknown family {case['family']!r}")
    return problems


# --- analysis -------------------------------------------------------------


def analyse(tests: list[dict[str, Any]]) -> dict[str, Any]:
    scores: dict[str, list[float]] = {m: [] for m in MODES}
    latency: dict[str, list[float]] = {m: [] for m in MODES}
    traps: dict[str, int] = {m: 0 for m in MODES}
    empties: dict[str, int] = {m: 0 for m in MODES}
    by_family: dict[str, dict[str, list[float]]] = defaultdict(lambda: {m: [] for m in MODES})
    wins: dict[str, float] = {m: 0.0 for m in MODES}

    for test in tests:
        best = max(test["runs"][m]["score"] for m in MODES)
        winners = [m for m in MODES if test["runs"][m]["score"] == best]
        for m in MODES:
            run = test["runs"][m]
            scores[m].append(run["score"])
            latency[m].append(run["latency_ms"])
            traps[m] += run["components"]["traps_hit"]
            empties[m] += 1 if run["components"]["empty"] else 0
            by_family[test["family"]][m].append(run["score"])
        for m in winners:
            wins[m] += 1.0 / len(winners)

    leaderboard = sorted(
        (
            {
                "mode": m,
                "label": MODE_LABELS[m],
                "mean": round(sum(scores[m]) / len(scores[m]), 2),
                "best": max(scores[m]),
                "worst": min(scores[m]),
                "wins": round(wins[m], 2),
                "traps_retrieved": traps[m],
                "empty_answers": empties[m],
                "median_latency_ms": round(_median(latency[m]), 1),
            }
            for m in MODES
        ),
        key=lambda r: -r["mean"],
    )

    family_rows = [
        {
            "family": f["id"],
            "blurb": f["blurb"],
            "tests": len(next(iter(by_family[f["id"]].values()))) if f["id"] in by_family else 0,
            "scores": {m: round(sum(v) / len(v), 2) for m, v in by_family[f["id"]].items()},
        }
        for f in FAMILIES
        if f["id"] in by_family
    ]

    return {
        "leaderboard": leaderboard,
        "by_family": family_rows,
        "findings": _findings(tests, leaderboard, scores, traps, empties),
        "totals": {
            "tests": len(tests),
            "modes": len(MODES),
            "retrievals": len(tests) * len(MODES),
            "judgments": sum(len(t["gold"]) + len(t["traps"]) for t in tests),
            "traps_planted": sum(len(t["traps"]) for t in tests),
        },
    }


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if not ordered:
        return 0.0
    return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def _by_id(tests: list[dict[str, Any]], test_id: str) -> dict[str, Any]:
    return next(t for t in tests if t["id"] == test_id)


def _findings(
    tests: list[dict[str, Any]],
    leaderboard: list[dict[str, Any]],
    scores: dict[str, list[float]],
    traps: dict[str, int],
    empties: dict[str, int],
) -> list[dict[str, Any]]:
    """Authored conclusions with every number computed from the run.

    The prose is fixed; the figures, the mode names and the test ids are
    interpolated from what actually happened. A conclusion that stops being
    true when the corpus or the rubric changes will read as obviously wrong
    rather than quietly going stale - which is the only reason to compute
    them rather than type them.
    """
    out: list[dict[str, Any]] = []
    by_mode = {row["mode"]: row for row in leaderboard}
    top, bottom = leaderboard[0], leaderboard[-1]

    def plural(n: int, word: str) -> str:
        return f"{n} {word}{'' if n == 1 else 's'}"

    # 1. The mean is a property of the question mix, not of the mode.
    lexical = _by_id(tests, "exact-name")
    kw_lex = lexical["runs"]["keyword"]["score"]
    kw_rest = [t["runs"]["keyword"]["score"] for t in tests if t["id"] != "exact-name"]
    out.append({
        "title": "There is no best retrieval mode, only a best mode per question shape",
        "body": (
            f"{top['label']} leads on mean score ({top['mean']}/5) and {bottom['label']} "
            f"trails it ({bottom['mean']}/5), and that ordering tells you almost nothing "
            f"on its own. Keyword search scores {kw_lex}/5 on the lexical control - "
            f"matching the best result any mode achieved on it, at "
            f"{by_mode['keyword']['median_latency_ms']} ms against "
            f"{by_mode['hybrid']['median_latency_ms']} ms - and averages "
            f"{round(sum(kw_rest) / len(kw_rest), 2)}/5 across the other "
            f"{len(kw_rest)} questions. A mean over a question mix somebody chose is a "
            f"statement about the mix. Change it and you change the winner."
        ),
        "evidence": ["exact-name"],
    })

    # 2. Dense retrieval has no abstention.
    sem_low = [t["id"] for t in tests if t["runs"]["semantic"]["score"] <= 1.5]
    out.append({
        "title": "Semantic search never returns nothing, which is exactly the problem",
        "body": (
            f"The vector leg returned a full page of {K} ranked results on every one of "
            f"the {len(tests)} questions, including the {len(sem_low)} where it scored "
            f"1.5/5 or below. There is no similarity floor and no abstention: cosine "
            f"distance always produces an ordering, so a question this corpus cannot "
            f"answer looks exactly like one it can. Keyword search returned nothing on "
            f"{plural(empties['keyword'], 'question')} in the same suite. That is a worse "
            f"experience and strictly better information."
        ),
        "evidence": sem_low[:3],
    })

    # 3. Traps are eaten by whoever matches on surface features.
    distinct_traps = {t_id for t in tests for t_id in (x["id"] for x in t["traps"])}
    trap_order = sorted(MODES, key=lambda m: -traps[m])
    clean = [MODE_LABELS[m] for m in MODES if traps[m] == 0]
    out.append({
        "title": "Traps are eaten by whoever matches on surface features",
        "body": (
            f"This suite designates {len(distinct_traps)} documents as traps: wrong for "
            f"the question, and tempting to one specific failure mode. Across the suite "
            f"{MODE_LABELS[trap_order[0]]} "
            f"retrieved {traps[trap_order[0]]} of them and "
            f"{MODE_LABELS[trap_order[1]]} retrieved {traps[trap_order[1]]}"
            + (f"; {', '.join(clean)} retrieved none" if clean else "")
            + ". A trap only works if the retriever is matching something the document "
            f"has and the answer does not: a shared string, a shared topic, a plausible "
            f"headline. Modes that match against modelled structure cannot be fooled by "
            f"prose, because they never read any."
        ),
        "evidence": ["beef-word-trap", "headline-lie"],
    })

    # 4. Fusion inherits its best leg - in both directions.
    neg = _by_id(tests, "negation")
    out.append({
        "title": "Fusion inherits its best leg, and its worst",
        "body": (
            f"On the negation question keyword scored "
            f"{neg['runs']['keyword']['score']}/5 and semantic "
            f"{neg['runs']['semantic']['score']}/5 - both answered a question about the "
            f"absence of conflict with documents about conflict. Hybrid scored "
            f"{neg['runs']['hybrid']['score']}/5 anyway, because the graph leg used "
            f"NOT EXISTS and RRF weights it 2.5x, which was enough to outvote two legs "
            f"agreeing with each other and not with the question. Then hybrid + ontology "
            f"scored {neg['runs']['hybrid_ontology']['score']}/5 on the identical "
            f"question, because the expansion recognised 'conflict' as a modelled class "
            f"and rewrote the graph leg into a CONFLICT_WITH traversal - turning the one "
            f"leg that was right into the one that was most confidently wrong. Fusion did "
            f"not detect anything in either direction. It counted votes."
        ),
        "evidence": ["negation"],
    })

    # 5. The ontology's real position in this suite.
    deltas = [
        (t["id"], round(t["runs"]["hybrid_ontology"]["score"] - t["runs"]["hybrid"]["score"], 1))
        for t in tests
    ]
    helped = [d for d in deltas if d[1] > 0]
    hurt = [d for d in deltas if d[1] < 0]
    unchanged = [d for d in deltas if d[1] == 0]
    onto_vs_text = round(
        by_mode["hybrid_ontology"]["mean"] - max(by_mode["keyword"]["mean"], by_mode["semantic"]["mean"]), 2
    )
    out.append({
        "title": "The ontology beats text retrieval comfortably and never beat plain hybrid here",
        "body": (
            f"Against the text modes the case is emphatic: hybrid + ontology averages "
            f"{by_mode['hybrid_ontology']['mean']}/5 against "
            f"{by_mode['semantic']['mean']}/5 for semantic, a gap of {onto_vs_text} "
            f"points. Against plain hybrid it is not: across {len(tests)} questions "
            f"{len(helped)} improved, {len(unchanged)} were unchanged and {len(hurt)} got "
            f"worse"
            + (f" ({', '.join(d[0] for d in hurt)})" if hurt else "")
            + ". Two things are going on and only one of them is about ontologies. The "
            f"expansion widens the keyword and vector legs with class synonyms, which "
            f"costs precision when the widened terms match a trap. And this suite pins "
            f"the plan, which hands plain hybrid a hand-written Cypher that already "
            f"encodes the very translations the ontology exists to derive. That is a real "
            f"limitation of the experiment rather than a result: run it with "
            f"--live-planner and the comparison is against Cypher a model wrote, which is "
            f"the comparison that actually matters in production. What holds either way "
            f"is the cost side - hybrid + ontology is the slowest mode in the suite at "
            f"{by_mode['hybrid_ontology']['median_latency_ms']} ms median."
        ),
        "evidence": [d[0] for d in hurt[:2]] or ["showcase-two-hop"],
    })

    # 6. The eval found bugs in the corpus.
    kentucky = _by_id(tests, "structured-group")
    out.append({
        "title": "Writing the judgments found three places where the prose and the records disagree",
        "body": (
            "Grading against ground truth rather than against output surfaced "
            "contradictions inside the corpus itself. One article is titled 'He was "
            "traded twice before he turned twenty-six'; the trade ledger records one "
            "trade for that player. Another is titled 'Two former teammates meet in the "
            "conference finals'; neither player carries a FORMER_TEAMMATE edge, because "
            "their season ranges never overlap. A third names six players from one "
            f"college and the database holds eight, which is why keyword search scores "
            f"{kentucky['runs']['keyword']['score']}/5 there while looking entirely "
            f"successful. Every text mode believes all three, because believing the "
            f"document is the only thing a text mode does. None of this was planted; it "
            f"was in the corpus before the report existed and nothing in the app "
            f"surfaced it. That is the actual argument for writing an eval."
        ),
        "evidence": ["counting", "headline-lie", "structured-group"],
    })

    # 7. Schema ceilings.
    ledger = _by_id(tests, "pick-ledger")
    ledger_best = ledger["best_score"]
    out.append({
        "title": "A mode's ceiling is set by the schema, not only by the technique",
        "body": (
            f"Graph search scored {ledger['runs']['graph']['score']}/5 on the draft-pick "
            f"question - its worst result in the suite - and the technique is not at "
            f"fault. Draft picks were modelled as rows on a relational table rather than "
            f"as nodes and edges, so there is nothing to traverse and the best available "
            f"Cypher counts trades instead. No mode cleared {ledger_best}/5 on it. The "
            f"same question expressed as SQL over trade_picks is four lines. It is left "
            f"in the report on purpose: modelling decisions made long before any query "
            f"ran set the ceiling on what retrieval over that data can do, and a "
            f"benchmark that quietly routes around its own schema gaps is measuring its "
            f"author rather than the system."
        ),
        "evidence": ["pick-ledger"],
    })

    # 8. Variance and the shape of failure.
    spreads = {m: round(max(scores[m]) - min(scores[m]), 1) for m in MODES}
    widest = max(spreads, key=lambda m: spreads[m])
    graph_low = sorted(tests, key=lambda t: t["runs"]["graph"]["score"])[0]
    out.append({
        "title": "Failure has a different shape in each mode",
        "body": (
            f"{MODE_LABELS[widest]} has the widest spread in the suite "
            f"({min(scores[widest])} to {max(scores[widest])}), but spread is the less "
            f"interesting half. The text modes fail gradually: a slightly wrong page, "
            f"ranked confidently, with a plausible top result. Graph search fails "
            f"discontinuously - the Cypher either describes the question or it does not, "
            f"and its floor in this suite is {min(scores['graph'])}/5, on "
            f"'{graph_low['query']}'. Pattern matching has no partial credit, which is a "
            f"virtue when a wrong answer is expensive and a liability when any answer "
            f"beats none. Note too that every graph and ontology score here presumes "
            f"correct Cypher, which was written by hand; in the live app a model writes "
            f"it and can be wrong in ways this report does not measure."
        ),
        "evidence": [graph_low["id"], "showcase-two-hop"],
    })

    return out


# --- report ---------------------------------------------------------------


def build_report(live_planner: bool = False) -> dict[str, Any]:
    print("[eval] building index…", flush=True)
    index.build()

    # The first embed call loads the ONNX model, which takes seconds. Left
    # unwarmed it lands entirely on whichever test happens to run first and
    # makes the latency column a lie.
    embed_query("warm the onnxruntime session before anything is timed")

    resolver = Resolver(index)

    problems = validate(resolver)
    if problems:
        for p in problems:
            print(f"[eval] INVALID: {p}", file=sys.stderr)
        raise SystemExit("Suite validation failed. Fix the judgments before generating a report.")

    plan_source = "pinned"
    planner_note = (
        "Every mode ran the same hand-written plan, so this report measures retrieval "
        "rather than the planner. The plans are in app/evaluation/suite.py and no "
        "Anthropic API call was made."
    )
    if live_planner:
        from ..planner import planner as live

        plan_source = f"live ({PLANNER_MODEL})"
        planner_note = (
            f"Plans were generated by {PLANNER_MODEL} at run time. Scores include planner "
            "variance, so two runs of this report may differ."
        )

    tests: list[dict[str, Any]] = []
    for i, case in enumerate(TEST_CASES, start=1):
        print(f"[eval] {i}/{len(TEST_CASES)}  {case['id']}", flush=True)
        if live_planner:
            case = {**case, "plan": {**case["plan"], **live.plan(case["query"])}}
        runs = {m: evaluate(index, resolver, case, m) for m in MODES}
        best = max(runs[m]["score"] for m in MODES)
        tests.append(
            {
                "id": case["id"],
                "family": case["family"],
                "query": case["query"],
                "headline": case["headline"],
                "preamble": case["preamble"],
                "what_good_looks_like": case["what_good_looks_like"],
                "plan": case["plan"],
                "gold": _gold_table(index, case["judgments"]),
                "traps": [
                    {"id": doc_id, "title": _title(index, doc_id), "reason": reason}
                    for doc_id, reason in case["traps"].items()
                ],
                "runs": runs,
                "best_mode": [m for m in MODES if runs[m]["score"] == best],
                "best_score": best,
                "spread": round(best - min(runs[m]["score"] for m in MODES), 1),
            }
        )

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "environment": {
            "python": platform.python_version(),
            "embed_model": EMBED_MODEL,
            "vector_engine": index.build_report.get("vector_engine", ""),
            "corpus": index.build_report.get("tables", {}),
        },
        "planner": {"source": plan_source, "note": planner_note},
        "rubric": scoring.RUBRIC,
        "modes": [{"id": m, "label": MODE_LABELS[m]} for m in MODES],
        "families": FAMILIES,
        "how_to_reproduce": "cd apps/api && python -m app.evaluation.runner",
        "caveats": [
            "Twelve questions is a demonstration, not a benchmark. Every one was written "
            "by the same person who wrote the corpus and the retrievers, which is the "
            "oldest way there is to build an eval that flatters your own system.",
            "Relevance judgments are one person's opinion, applied consistently. They are "
            "published in full above each test so you can disagree with a specific one.",
            "The rubric is arithmetic chosen to be legible, not a standard IR metric. "
            "Weighting the three components differently reorders the leaderboard.",
            "Graph and ontology scores presume correct Cypher. In the live app that Cypher "
            "comes from a model and can be wrong; here it was written by hand.",
        ],
        "tests": tests,
        "analysis": analyse(tests),
    }


def _gold_table(idx: ArenaIndex, judgments: dict[str, int]) -> list[dict[str, Any]]:
    names = {ANSWERS: "Answers", EVIDENCE: "Evidence", TOPICAL: "Topical"}
    rows = [
        {"id": doc_id, "grade": grade, "grade_name": names.get(grade, str(grade)),
         "title": _title(idx, doc_id)}
        for doc_id, grade in judgments.items()
    ]
    return sorted(rows, key=lambda r: (-r["grade"], r["id"]))


def _title(idx: ArenaIndex, doc_id: str) -> str:
    kind, _, ref = doc_id.partition(":")
    if kind == "player":
        player = idx.player(ref)
        return player["name"] if player else ref
    if kind == "article":
        article = idx.article(ref)
        return article["title"] if article else ref
    if kind == "team":
        assert idx.conn is not None
        row = idx.conn.execute("SELECT name FROM teams WHERE id = ?", (ref,)).fetchone()
        return row["name"] if row else ref
    return ref


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-planner", action="store_true",
                        help="use the Claude planner instead of the pinned plans")
    parser.add_argument("--check", action="store_true",
                        help="compare against the committed report and exit 1 on drift")
    args = parser.parse_args()

    started = time.perf_counter()
    report = build_report(live_planner=args.live_planner)

    if args.check:
        if not REPORT_PATH.exists():
            raise SystemExit(f"No committed report at {REPORT_PATH}")
        committed = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        drift = [
            f"{t['id']}/{m}: {c['runs'][m]['score']} -> {t['runs'][m]['score']}"
            for t, c in zip(report["tests"], committed["tests"])
            for m in MODES
            if t["runs"][m]["score"] != c["runs"][m]["score"]
        ]
        if drift:
            print("[eval] scores drifted from the committed report:")
            for line in drift:
                print(f"  {line}")
            raise SystemExit(1)
        print("[eval] no drift.")
        return

    REPORT_PATH.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    size_kb = REPORT_PATH.stat().st_size / 1024
    print(f"[eval] wrote {REPORT_PATH} ({size_kb:.0f} KB) in {time.perf_counter() - started:.1f}s")
    for row in report["analysis"]["leaderboard"]:
        print(f"       {row['label']:<18} mean {row['mean']:>4}/5   wins {row['wins']:>5}"
              f"   traps {row['traps_retrieved']}")


if __name__ == "__main__":
    main()
