"""Semantic retrieval: local ONNX embeddings, cosine KNN in sqlite-vec."""

from __future__ import annotations

import time
from typing import Any

from ..config import EMBED_DIM, EMBED_MODEL
from ..index import ArenaIndex
from ..schemas import ExecutedStep, ResultItem
from ..stores.vectors import embed_query
from .common import doc_to_result


def run(
    idx: ArenaIndex, semantic_query: str, limit: int, *, label: str = "Semantic retrieval (cosine KNN)"
) -> tuple[list[ExecutedStep], list[ResultItem], list[str]]:
    assert idx.vectors is not None

    t0 = time.perf_counter()
    qvec = embed_query(semantic_query)
    embed_ms = round((time.perf_counter() - t0) * 1000, 2)

    embed_step = ExecutedStep(
        label="Embed the rewritten query",
        language="python",
        code=(
            f'model = TextEmbedding("{EMBED_MODEL}")\n'
            f"# bge models take an instruction prefix on the query side only\n"
            f"query_vector = next(model.query_embed([\n"
            f"    {semantic_query!r}\n"
            f"]))\n"
            f"# -> float32[{EMBED_DIM}], L2-normalised"
        ),
        params={"text": semantic_query},
        engine=f"fastembed / onnxruntime ({EMBED_MODEL})",
        row_count=1,
        latency_ms=embed_ms,
        note=(
            f"The whole corpus was embedded once at startup with the same model. "
            f"Only this one vector is computed per query."
        ),
    )

    t0 = time.perf_counter()
    hits, engine, code = idx.vectors.search(qvec, limit)
    search_ms = round((time.perf_counter() - t0) * 1000, 2)

    results: list[ResultItem] = []
    for rank, (rowid, similarity) in enumerate(hits, start=1):
        doc = idx.doc_by_rowid(rowid)
        results.append(
            doc_to_result(
                doc,
                score=similarity,
                rank=rank,
                breakdown={
                    "cosine_similarity": round(similarity, 4),
                    "cosine_distance": round(1 - similarity, 4),
                    "dimensions": EMBED_DIM,
                },
                why=(
                    "Its embedding sits close to the query's embedding. No word in "
                    "your question needs to appear in this document at all."
                ),
            )
        )

    search_step = ExecutedStep(
        label=label,
        language="sql" if engine == "sqlite-vec" else "python",
        code=code,
        params={"query_vector": f"<float32[{EMBED_DIM}]>", "k": limit},
        engine=engine,
        row_count=len(results),
        latency_ms=search_ms,
        note=(
            "Cosine distance over unit vectors. Every document in the corpus gets a "
            "score, so this always returns k results - including when nothing is "
            "actually relevant."
        ),
    )

    warnings: list[str] = []
    if engine == "numpy-fallback":
        warnings.append(
            "The sqlite-vec extension could not be loaded, so vector search ran as a "
            "numpy scan. The results are identical; the SQL shown is the numpy code "
            "that actually executed."
        )
    return [embed_step, search_step], results, warnings


EXPLAIN: dict[str, Any] = {
    "what_happened": (
        "Your question was rewritten as a declarative sentence, embedded into a "
        f"{EMBED_DIM}-dimensional vector with {EMBED_MODEL}, and compared against a "
        "pre-computed vector for every document by cosine similarity."
    ),
    "strengths": [
        "Finds paraphrase: 'bad blood' and 'rift' match a query about feuds.",
        "Survives typos, synonyms and vocabulary you did not think of.",
        "Needs no schema knowledge from the person asking.",
    ],
    "limits": [
        "It always returns k results, ranked. Nothing tells you the top hit is bad.",
        "Precision on names and numbers is poor - embeddings blur exact tokens.",
        "It confuses topic with intent: an article about the ABSENCE of conflict "
        "embeds close to one about conflict.",
        "It cannot count, filter by a threshold, or traverse a relationship.",
    ],
}
