"""Keyword retrieval: SQLite FTS5, real BM25, no semantics whatsoever."""

from __future__ import annotations

import sqlite3
import time
from typing import Any

from ..index import ArenaIndex
from ..schemas import ExecutedStep, ResultItem
from .common import doc_to_result

SQL = """SELECT d.doc_rowid, d.id, d.kind, d.ref_id, d.title, d.body, d.meta,
       bm25(documents_fts, 2.0, 1.0)                      AS bm25_score,
       snippet(documents_fts, 1, '[', ']', ' … ', 14)     AS excerpt
FROM documents_fts
JOIN documents AS d ON d.doc_rowid = documents_fts.rowid
WHERE documents_fts MATCH :match_expression
ORDER BY bm25_score          -- FTS5 returns BM25 negated, so ascending is best-first
LIMIT :limit"""


def run(
    idx: ArenaIndex, match_expression: str, limit: int, *, label: str = "Keyword retrieval (BM25)"
) -> tuple[ExecutedStep, list[ResultItem], list[str]]:
    assert idx.conn is not None
    params = {"match_expression": match_expression, "limit": limit}
    started = time.perf_counter()
    error = ""
    rows: list[sqlite3.Row] = []
    try:
        rows = idx.conn.execute(SQL, params).fetchall()
    except sqlite3.OperationalError as exc:
        error = f"FTS5 rejected the match expression: {exc}"
    elapsed = round((time.perf_counter() - started) * 1000, 2)

    results: list[ResultItem] = []
    for rank, row in enumerate(rows, start=1):
        doc = ArenaIndex._doc(row)
        bm25 = row["bm25_score"]
        results.append(
            doc_to_result(
                doc,
                score=-bm25,
                rank=rank,
                snippet=row["excerpt"],
                breakdown={
                    "bm25_raw": round(bm25, 4),
                    "bm25_display": round(-bm25, 4),
                    "title_weight": 2.0,
                    "body_weight": 1.0,
                },
                why=(
                    "Matched the literal terms in the FTS5 expression. BM25 rewards "
                    "rare terms and short documents; it has no idea what any word means."
                ),
            )
        )

    step = ExecutedStep(
        label=label,
        language="sql",
        code=SQL,
        params=params,
        engine="SQLite 3 FTS5 (porter unicode61 tokenizer)",
        row_count=len(results),
        latency_ms=elapsed,
        error=error,
        note=(
            "BM25 scores come back negative from FTS5 (more negative is a better "
            "match), which is why the ORDER BY is ascending."
        ),
    )
    warnings = [error] if error else []
    return step, results, warnings


EXPLAIN: dict[str, Any] = {
    "what_happened": (
        "Your question was turned into an FTS5 match expression and scored with BM25 "
        "over an inverted index. Documents are ranked by how many of your exact terms "
        "they contain, weighted by how rare each term is across the corpus."
    ),
    "strengths": [
        "Exact, fast and completely explainable - you can point at the matched tokens.",
        "Unbeatable for names, codes, error strings and anything you can spell exactly.",
        "No model, no embedding, no cost. It runs in under a millisecond here.",
    ],
    "limits": [
        "It matches strings, not meaning: 'beef' retrieves the brisket article.",
        "A document that says 'bad blood' is invisible to a search for 'feud'.",
        "It cannot answer anything relational - 'former teammates' is just two words.",
    ],
}
