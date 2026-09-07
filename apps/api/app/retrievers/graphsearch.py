"""Graph retrieval: real Cypher against an embedded Kuzu database.

Unlike the two text modes, this one does not rank. It either matches a pattern
or it does not, and the rows it returns are the answer rather than candidates
for a human to skim.
"""

from __future__ import annotations

import time
from typing import Any

from ..index import ArenaIndex
from ..schemas import ExecutedStep, ResultItem


def run(
    idx: ArenaIndex,
    cypher: str,
    limit: int,
    *,
    label: str = "Graph traversal (Cypher)",
    note: str = "",
    repair: Any = None,
    question: str = "",
) -> tuple[list[ExecutedStep], list[ResultItem], list[str], bool]:
    """Execute Cypher, optionally repairing it once if Kuzu rejects it."""
    assert idx.graph is not None
    steps: list[ExecutedStep] = []
    warnings: list[str] = []
    repaired = False

    if not cypher.strip():
        steps.append(
            ExecutedStep(
                label=label,
                language="cypher",
                code="",
                engine="Kuzu (embedded)",
                error="The planner judged this question to have no graph expression.",
                note=(
                    "That is a real answer, not a failure. Plenty of questions are "
                    "about text, not about relationships."
                ),
            )
        )
        return steps, [], warnings, repaired

    cols, rows, error, elapsed = _execute(idx, cypher, limit)

    if error and repair is not None:
        warnings.append(f"First Cypher attempt failed, retried once. Original error: {error}")
        steps.append(
            ExecutedStep(
                label=f"{label} - first attempt",
                language="cypher",
                code=cypher,
                engine="Kuzu (embedded)",
                error=error,
                latency_ms=elapsed,
                note="Rejected by the parser. Sent back to the planner with the error.",
            )
        )
        try:
            cypher = repair(question, cypher, error)
            repaired = True
            cols, rows, error, elapsed = _execute(idx, cypher, limit)
        except Exception as exc:  # noqa: BLE001
            error = f"{error} (repair also failed: {exc})"

    steps.append(
        ExecutedStep(
            label=label,
            language="cypher",
            code=cypher,
            engine="Kuzu (embedded property graph)",
            row_count=len(rows),
            latency_ms=elapsed,
            error=error,
            note=note or (
                "Pattern matching, not ranking. Five of the relationship types "
                "traversed here were derived at build time and appear in no source file."
            ),
            table={"columns": cols, "rows": rows} if cols else None,
        )
    )

    return steps, _hydrate(idx, cols, rows), warnings, repaired


def _execute(idx: ArenaIndex, cypher: str, limit: int) -> tuple[list[str], list[list], str, float]:
    assert idx.graph is not None
    started = time.perf_counter()
    try:
        cols, rows = idx.graph.query(cypher, limit=max(limit, 25))
        error = ""
    except Exception as exc:  # noqa: BLE001 - Kuzu raises RuntimeError for parse errors
        cols, rows, error = [], [], str(exc).strip()
    return cols, rows, error, round((time.perf_counter() - started) * 1000, 2)


def _hydrate(idx: ArenaIndex, cols: list[str], rows: list[list]) -> list[ResultItem]:
    """Turn Cypher rows into result cards, enriching any `id` column."""
    results: list[ResultItem] = []
    for rank, row in enumerate(rows, start=1):
        record = dict(zip(cols, row))
        entity_id = record.get("id")

        player = idx.player(entity_id) if isinstance(entity_id, str) else None
        if player:
            extras = {k: v for k, v in record.items() if k not in ("id", "name")}
            detail = ", ".join(f"{k}: {v}" for k, v in extras.items() if v is not None)
            results.append(
                ResultItem(
                    id=f"player:{player['id']}",
                    kind="player",
                    title=player["name"],
                    snippet=(
                        f"{player['position']} · {player['team_name']} · "
                        f"{player['ppg']} ppg · age {player['age']}"
                        + (f" — {detail}" if detail else "")
                    ),
                    score=1.0,
                    rank=rank,
                    why="Matched the graph pattern. Graph results are exact, not scored.",
                    data={"row": record, "player": player},
                )
            )
            continue

        article = idx.article(entity_id) if isinstance(entity_id, str) else None
        if article:
            results.append(
                ResultItem(
                    id=f"article:{article['id']}",
                    kind="article",
                    title=article["title"],
                    snippet=article["body"][:240],
                    score=1.0,
                    rank=rank,
                    why="Matched the graph pattern.",
                    data={"row": record, "published_at": article["published_at"]},
                )
            )
            continue

        label = " · ".join(f"{k}={v}" for k, v in record.items() if v is not None)
        results.append(
            ResultItem(
                id=f"row:{rank}",
                kind="path",
                title=label[:120] or "(empty row)",
                snippet="",
                score=1.0,
                rank=rank,
                why="A projected row rather than a document.",
                data={"row": record},
            )
        )
    return results


EXPLAIN: dict[str, Any] = {
    "what_happened": (
        "Your question was compiled into a Cypher pattern and matched against a "
        "property graph of players, teams, articles and trades. Rows come back "
        "because they satisfy the pattern, not because they scored well."
    ),
    "strengths": [
        "Answers relational questions text search cannot express at all: "
        "'traded twice', 'former teammates who later fought'.",
        "Exact and complete - no ranking means no silent truncation of the answer.",
        "Traverses derived edges. FORMER_TEAMMATE is computed from overlapping "
        "season ranges and exists in no source file.",
    ],
    "limits": [
        "Brittle. One wrong label or property name and you get zero rows, not "
        "approximately-right rows.",
        "Only sees what was modelled. A person mentioned in an article but absent "
        "from the graph is invisible.",
        "It has no notion of 'about' - it cannot find an article on a theme.",
        "Someone, or something, has to write correct Cypher first.",
    ],
}
