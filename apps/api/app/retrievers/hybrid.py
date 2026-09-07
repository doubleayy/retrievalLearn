"""Hybrid retrieval, with and without the ontology.

Both variants run the same three retrievers and fuse them with Reciprocal Rank
Fusion. The only difference is that the ontology variant rewrites the three
queries first, using the domain model rather than the language model.
"""

from __future__ import annotations

from typing import Any

from ..expansion import Expansion, expand, widen_keyword, widen_semantic
from ..index import ArenaIndex
from ..schemas import ExecutedStep, OntologyTrace, ResultItem
from . import graphsearch, keyword, semantic
from .common import LEG_WEIGHTS, RRF_K, reciprocal_rank_fusion


def run(
    idx: ArenaIndex,
    plan: dict,
    limit: int,
    *,
    use_ontology: bool,
    question: str,
    repair: Any = None,
) -> tuple[list[ExecutedStep], list[ResultItem], dict[str, Any], OntologyTrace | None, list[str], bool]:
    steps: list[ExecutedStep] = []
    warnings: list[str] = []
    trace: OntologyTrace | None = None
    repaired = False

    keyword_query = plan.get("keyword_query", "")
    semantic_query = plan.get("semantic_query", "")
    cypher = plan.get("cypher", "")
    graph_note = ""

    if use_ontology:
        exp = expand(question, idx.onto, plan.get("ontology_terms", []))
        steps.append(_expansion_step(exp, idx))
        trace = _trace(exp, idx)
        if exp.matches:
            keyword_query = widen_keyword(keyword_query, exp)
            semantic_query = widen_semantic(semantic_query, exp)
            if exp.cypher:
                cypher = exp.cypher
                graph_note = exp.cypher_note
        else:
            warnings.append(
                "No phrase in this question matched the ontology, so this mode is "
                "behaving exactly like plain hybrid. That is itself the lesson: an "
                "ontology only helps where the domain has been modelled."
            )

    kw_step, kw_results, kw_warn = keyword.run(
        idx, keyword_query, limit * 2, label="1. Keyword leg (BM25)"
    )
    steps.append(kw_step)
    warnings.extend(kw_warn)

    sem_steps, sem_results, sem_warn = semantic.run(
        idx, semantic_query, limit * 2, label="2. Vector leg (cosine KNN)"
    )
    steps.extend(sem_steps)
    warnings.extend(sem_warn)

    graph_steps, graph_results, graph_warn, repaired = graphsearch.run(
        idx,
        cypher,
        limit * 2,
        label="3. Graph leg (Cypher)",
        note=graph_note,
        repair=repair,
        question=question,
    )
    steps.extend(graph_steps)
    warnings.extend(graph_warn)

    rankings: dict[str, list[str]] = {
        "keyword": [r.id for r in kw_results],
        "semantic": [r.id for r in sem_results],
    }
    graph_ids = [r.id for r in graph_results if r.kind in ("player", "article")]
    if graph_ids:
        rankings["graph"] = graph_ids

    order, detail = reciprocal_rank_fusion(rankings)

    # Graph first: when the same entity is found by two legs, the graph card
    # carries the relationship detail, which is the more useful presentation.
    lookup: dict[str, ResultItem] = {}
    for item in graph_results + sem_results + kw_results:
        lookup.setdefault(item.id, item)

    fused: list[ResultItem] = []
    for rank, doc_id in enumerate(order[:limit], start=1):
        item = lookup.get(doc_id)
        if item is None:
            continue
        sources = detail[doc_id]["sources"]
        fused.append(
            item.model_copy(
                update={
                    "rank": rank,
                    "score": detail[doc_id]["total"],
                    "score_breakdown": {"rrf": detail[doc_id], "original": item.score_breakdown},
                    "why": _why(sources),
                }
            )
        )

    # Graph rows that are not documents (counts, projections) still deserve to be seen.
    for item in graph_results:
        if item.kind == "path" and len(fused) < limit:
            fused.append(item.model_copy(update={"rank": len(fused) + 1}))

    fusion = {
        "method": "weighted reciprocal rank fusion",
        "k": RRF_K,
        "weights": {name: LEG_WEIGHTS.get(name, 1.0) for name in rankings},
        "formula": "score(d) = Σ over legs of weight_leg / (k + rank_leg(d))",
        "why": (
            "BM25 and cosine similarity are on incomparable scales, so their raw "
            "scores cannot be added. RRF throws the scores away and keeps only the "
            "ranks, which is why it is the default in practice. The graph leg is "
            "weighted higher because a pattern match is a stronger claim than a "
            "good position in a ranked list."
        ),
        "legs": {name: len(ids) for name, ids in rankings.items()},
        "detail": {doc_id: detail[doc_id] for doc_id in order[:limit]},
    }
    return steps, fused, fusion, trace, warnings, repaired


def _why(sources: dict[str, Any]) -> str:
    names = list(sources)
    if len(names) == 1:
        return f"Found by the {names[0]} leg only (rank {sources[names[0]]['rank']})."
    parts = ", ".join(f"{n} #{sources[n]['rank']}" for n in names)
    return f"Agreed on by {len(names)} legs — {parts}. Agreement is what lifts it."


def _expansion_step(exp: Expansion, idx: ArenaIndex) -> ExecutedStep:
    if not exp.matches:
        return ExecutedStep(
            label="0. Ontology expansion",
            language="text",
            code="(no phrase in the question matched a class or property)",
            engine="in-process OWL-lite reasoner",
            note="Nothing to expand, so the remaining legs run unmodified.",
        )
    lines = []
    for m in exp.matches:
        arrow = f'"{m["phrase"]}"'.ljust(24)
        if m["kind"] == "class":
            eq = f"  ≡ {m['equivalent_to']}" if m.get("equivalent_to") else ""
            lines.append(f"{arrow} → hoops:{m['resolved_to']}{eq}")
        else:
            derived = " (derived)" if m.get("derived") else ""
            lines.append(f"{arrow} → hoops:{m['resolved_to']} → [:{m.get('graph_rel','')}]{derived}")
    lines.append("")
    lines.append(f"subclass closure ({len(exp.classes)} classes):")
    lines.append("  " + ", ".join(exp.classes))
    if exp.sql_predicates:
        lines.append("")
        lines.append("structured predicates:")
        for p in exp.sql_predicates:
            lines.append(f"  {p}")
    if exp.conflict_kinds:
        lines.append("")
        lines.append("conflict subclasses admitted as values:")
        lines.append("  " + ", ".join(exp.conflict_kinds))
    return ExecutedStep(
        label="0. Ontology expansion",
        language="text",
        code="\n".join(lines),
        engine="in-process OWL-lite reasoner (no model call)",
        row_count=len(exp.matches),
        note=(
            "Deterministic and reproducible. This step is the only difference "
            "between this mode and plain hybrid."
        ),
    )


def _trace(exp: Expansion, idx: ArenaIndex) -> OntologyTrace:
    return OntologyTrace(
        matched_phrases=exp.matches,
        expanded_classes=exp.classes,
        expanded_synonyms=exp.synonyms,
        sql_predicates=exp.sql_predicates,
        derived_relations=exp.derived_relations,
        turtle=idx.onto.to_turtle(only=set(exp.classes)) if exp.classes else "",
    )


EXPLAIN_HYBRID: dict[str, Any] = {
    "what_happened": (
        "Three retrievers ran independently - BM25, vector KNN and a Cypher "
        "traversal - and their ranked lists were merged with Reciprocal Rank "
        "Fusion. A document that appears in two lists outranks one that tops "
        "a single list."
    ),
    "strengths": [
        "Covers each mode's blind spot: exact names from BM25, paraphrase from "
        "vectors, relationships from the graph.",
        "Agreement across legs is a genuine relevance signal.",
        "RRF needs no score calibration and no tuning.",
    ],
    "limits": [
        "Three times the work and three times the latency.",
        "It still only knows the words you used. 'Big men' is two tokens to BM25, "
        "a vague direction to the embedder, and nothing at all to Cypher.",
        "Fusion can bury a correct answer that only one leg found.",
    ],
}

EXPLAIN_ONTOLOGY: dict[str, Any] = {
    "what_happened": (
        "Before any retrieval ran, the question was parsed against a domain "
        "ontology. Phrases like 'big man' resolved to a class with an equivalence "
        "axiom, which became a position filter; 'beef' resolved to a class with "
        "seven subclasses; 'former teammate' resolved to a derived graph edge. "
        "Only then did the three legs run, on rewritten queries."
    ),
    "strengths": [
        "Turns vocabulary into structure: 'big man' becomes position IN ('PF','C'), "
        "which no amount of embedding similarity will give you.",
        "Subclass closure means asking about 'beef' also finds trade requests and "
        "locker room incidents, because they are modelled as kinds of conflict.",
        "Deterministic and auditable - the expansion is a proof you can read.",
        "Recovers precision the vector leg loses: the brisket article is never a "
        "member of any conflict class.",
    ],
    "limits": [
        "Someone has to build and maintain the ontology. This one is 200 lines "
        "of hand-written JSON.",
        "It only helps where the domain was modelled. Unmodelled phrases fall "
        "straight through to plain hybrid.",
        "Over-broad expansion hurts: pulling in all seven conflict subclasses "
        "surfaces a conduct suspension when you asked about interpersonal feuds.",
        "The closure has to be recomputed whenever the ontology changes.",
    ],
}
