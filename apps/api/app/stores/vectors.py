"""Dense vectors: a local ONNX embedding model plus sqlite-vec for KNN.

No embedding API key and no per-query cost. The model runs in the same
container as the API, which is why the first request after a cold start is
slower than the rest.

If the sqlite-vec extension cannot be loaded (some Python builds ship with
extension loading compiled out), we fall back to a numpy brute-force scan over
103 vectors. The fallback is reported honestly in the response so the UI never
shows SQL that did not actually run.
"""

from __future__ import annotations

import sqlite3
import struct
from typing import Any

import numpy as np

from ..config import EMBED_DIM, EMBED_MODEL, EMBED_THREADS

_model: Any = None


def get_model() -> Any:
    """Lazily construct the embedding model (it downloads on first use)."""
    global _model
    if _model is None:
        from fastembed import TextEmbedding

        _model = TextEmbedding(model_name=EMBED_MODEL, threads=EMBED_THREADS)
    return _model


def embed_passages(texts: list[str]) -> np.ndarray:
    vecs = list(get_model().embed(texts))
    return np.asarray(vecs, dtype=np.float32)


def embed_query(text: str) -> np.ndarray:
    """bge-* models expect an instruction prefix on the query side only.

    fastembed's `query_embed` applies it. Using `embed` for queries silently
    costs a few points of recall, which is a good demo of how much of
    "semantic search" is actually convention.
    """
    vec = next(iter(get_model().query_embed([text])))
    return np.asarray(vec, dtype=np.float32)


def _serialize(vec: np.ndarray) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec.tolist())


class VectorIndex:
    """Wraps whichever backend is available, and says which one it used."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.engine = "unavailable"
        self.matrix: np.ndarray | None = None
        self.rowids: list[int] = []

    def build(self, rowids: list[int], vectors: np.ndarray) -> None:
        self.rowids = rowids
        self.matrix = vectors
        try:
            import sqlite_vec

            self.conn.enable_load_extension(True)
            sqlite_vec.load(self.conn)
            self.conn.enable_load_extension(False)
            self.conn.execute(
                f"CREATE VIRTUAL TABLE doc_vectors USING vec0("
                f"  doc_rowid INTEGER PRIMARY KEY,"
                f"  embedding float[{EMBED_DIM}] distance_metric=cosine"
                f")"
            )
            self.conn.executemany(
                "INSERT INTO doc_vectors(doc_rowid, embedding) VALUES (?, ?)",
                [(rid, _serialize(v)) for rid, v in zip(rowids, vectors)],
            )
            self.conn.commit()
            self.engine = "sqlite-vec"
        except Exception:  # noqa: BLE001 - any failure means we use numpy
            self.engine = "numpy-fallback"

    # -- retrieval ---------------------------------------------------------

    SQL = """SELECT d.id, d.kind, d.ref_id, d.title, d.body, d.meta,
       vec_distance_cosine(v.embedding, :query_vector) AS distance
FROM doc_vectors AS v
JOIN documents AS d ON d.doc_rowid = v.doc_rowid
WHERE v.embedding MATCH :query_vector
  AND k = :k
ORDER BY distance"""

    NUMPY_SQL = """# sqlite-vec extension unavailable; brute-force cosine over 103 vectors
scores = doc_matrix @ query_vector      # both L2-normalised
top_k  = numpy.argsort(-scores)[:k]"""

    def search(self, query_vec: np.ndarray, k: int) -> tuple[list[tuple[int, float]], str, str]:
        """Returns [(doc_rowid, cosine_similarity)], the engine, and the code shown."""
        if self.engine == "sqlite-vec":
            rows = self.conn.execute(
                "SELECT doc_rowid, distance FROM doc_vectors "
                "WHERE embedding MATCH ? AND k = ? ORDER BY distance",
                (_serialize(query_vec), k),
            ).fetchall()
            return [(r["doc_rowid"], 1.0 - r["distance"]) for r in rows], self.engine, self.SQL

        assert self.matrix is not None
        sims = self.matrix @ query_vec
        order = np.argsort(-sims)[:k]
        return (
            [(self.rowids[i], float(sims[i])) for i in order],
            self.engine,
            self.NUMPY_SQL,
        )
