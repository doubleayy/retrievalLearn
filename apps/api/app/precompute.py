"""Embed the corpus ahead of time so the container boots fast.

Embedding 103 documents takes ~25 seconds of CPU. Paying that on every cold
start is the difference between a demo that feels instant and one that looks
broken. This runs during `docker build` instead, and the result is baked into
the image.

The cache is keyed by a fingerprint of the model name plus every document, so
editing a seed file automatically invalidates it rather than silently serving
stale vectors.

    python -m app.precompute
"""

from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path

import numpy as np

from .config import DATA_DIR, EMBED_MODEL
from .stores import relational

CACHE_PATH = DATA_DIR / "embeddings.npz"


def fingerprint(doc_ids: list[str], texts: list[str]) -> str:
    h = hashlib.sha256()
    h.update(EMBED_MODEL.encode())
    for doc_id, text in zip(doc_ids, texts):
        h.update(doc_id.encode())
        h.update(text.encode())
    return h.hexdigest()


def corpus(tmp_db: Path) -> tuple[list[int], list[str], list[str]]:
    conn = relational.build(tmp_db, DATA_DIR)
    docs = relational.all_documents(conn)
    conn.close()
    return (
        [d["doc_rowid"] for d in docs],
        [d["id"] for d in docs],
        [f"{d['title']}. {d['body']}" for d in docs],
    )


def load(doc_ids: list[str], texts: list[str]) -> np.ndarray | None:
    """Return the cached matrix if it matches this exact corpus, else None."""
    if not CACHE_PATH.exists():
        return None
    try:
        blob = np.load(CACHE_PATH, allow_pickle=False)
        if str(blob["fingerprint"]) != fingerprint(doc_ids, texts):
            return None
        return blob["matrix"].astype(np.float32)
    except Exception:  # noqa: BLE001 - a corrupt cache should just be ignored
        return None


def main() -> int:
    from .stores.vectors import embed_passages

    tmp_db = Path(CACHE_PATH.parent / "_precompute.db")
    rowids, doc_ids, texts = corpus(tmp_db)

    if load(doc_ids, texts) is not None:
        print(f"[precompute] {CACHE_PATH.name} is already current for this corpus, skipping.")
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(tmp_db) + suffix)
            if p.exists():
                p.unlink()
        return 0

    print(f"[precompute] embedding {len(texts)} documents with {EMBED_MODEL}…")
    started = time.perf_counter()
    matrix = embed_passages(texts)
    elapsed = time.perf_counter() - started

    np.savez_compressed(
        CACHE_PATH,
        matrix=matrix.astype(np.float32),
        rowids=np.asarray(rowids, dtype=np.int64),
        fingerprint=np.asarray(fingerprint(doc_ids, texts)),
    )
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(tmp_db) + suffix)
        if p.exists():
            p.unlink()

    size_kb = CACHE_PATH.stat().st_size / 1024
    print(
        f"[precompute] wrote {CACHE_PATH.name} "
        f"({matrix.shape[0]}×{matrix.shape[1]}, {size_kb:.0f} KB) in {elapsed:.1f}s"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
