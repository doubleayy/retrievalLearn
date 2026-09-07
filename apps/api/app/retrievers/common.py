"""Shared helpers: turning documents into result cards, and fusing rankings."""

from __future__ import annotations

from typing import Any

from ..schemas import ResultItem

RRF_K = 60


def doc_to_result(doc: dict[str, Any], *, score: float, rank: int, why: str,
                  breakdown: dict[str, Any], snippet: str = "") -> ResultItem:
    meta = doc.get("meta", {})
    kind = doc["kind"]
    return ResultItem(
        id=doc["id"],
        kind=kind,  # type: ignore[arg-type]
        title=doc["title"],
        snippet=snippet or _trim(doc["body"]),
        score=round(score, 4),
        rank=rank,
        score_breakdown=breakdown,
        why=why,
        data={
            "ref_id": doc["ref_id"],
            "published_at": meta.get("published_at", ""),
            "source_type": meta.get("source_type", ""),
            "conflict_kind": meta.get("conflict_kind"),
            "tags": meta.get("tags", []),
            "entities": meta.get("entities", []),
            "position": meta.get("position"),
            "team_id": meta.get("team_id"),
            "retrieval_note": meta.get("retrieval_note", ""),
        },
    )


def _trim(text: str, limit: int = 240) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


# The graph leg either matches a pattern or it does not, so a hit there is a
# stronger signal than placing well in a ranked list. Weighting it above the
# text legs is the difference between "Draymond Green" and a documentary about
# the 1980s tying for second place.
LEG_WEIGHTS: dict[str, float] = {"keyword": 1.0, "semantic": 1.0, "graph": 2.5}


def reciprocal_rank_fusion(
    rankings: dict[str, list[str]],
    k: int = RRF_K,
    weights: dict[str, float] | None = None,
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    """Weighted RRF.

    Each list is document ids in rank order. A document's fused score is the sum
    over lists of weight/(k + rank). Chosen over score normalisation because
    BM25 and cosine similarity are not on comparable scales and never will be.
    """
    weights = weights or LEG_WEIGHTS
    scores: dict[str, float] = {}
    detail: dict[str, dict[str, Any]] = {}
    for source, ids in rankings.items():
        weight = weights.get(source, 1.0)
        for position, doc_id in enumerate(ids, start=1):
            contribution = weight / (k + position)
            scores[doc_id] = scores.get(doc_id, 0.0) + contribution
            entry = detail.setdefault(doc_id, {"total": 0.0, "sources": {}})
            entry["sources"][source] = {
                "rank": position,
                "weight": weight,
                "contribution": round(contribution, 6),
            }
            entry["total"] = round(scores[doc_id], 6)
    order = sorted(scores, key=lambda d: -scores[d])
    return order, detail
