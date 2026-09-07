"""Everything the retrievers need, built once at startup and shared read-only."""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

from . import precompute
from .config import BUILD_DIR, DATA_DIR, KUZU_PATH, SQLITE_PATH
from .ontology import Ontology, get_ontology
from .stores import relational
from .stores.graph import GraphStore
from .stores.vectors import VectorIndex, embed_passages


class ArenaIndex:
    def __init__(self) -> None:
        self.conn: sqlite3.Connection | None = None
        self.vectors: VectorIndex | None = None
        self.graph: GraphStore | None = None
        self.onto: Ontology = get_ontology()
        self.build_report: dict[str, Any] = {}
        self.ready = False

    def build(self) -> None:
        BUILD_DIR.mkdir(parents=True, exist_ok=True)
        report: dict[str, Any] = {}

        t0 = time.perf_counter()
        self.conn = relational.build(SQLITE_PATH, DATA_DIR)
        report["sqlite_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        report["tables"] = relational.table_counts(self.conn)

        t0 = time.perf_counter()
        docs = relational.all_documents(self.conn)
        texts = [f"{d['title']}. {d['body']}" for d in docs]
        # Prefer the cache baked in at image build time. Embedding this corpus
        # from scratch costs ~25s of CPU, which is a poor cold start.
        matrix = precompute.load([d["id"] for d in docs], texts)
        report["embed_source"] = "precomputed" if matrix is not None else "computed at boot"
        if matrix is None:
            matrix = embed_passages(texts)
        self.vectors = VectorIndex(self.conn)
        self.vectors.build([d["doc_rowid"] for d in docs], matrix)
        report["embed_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        report["vector_engine"] = self.vectors.engine
        report["vectors"] = len(docs)

        t0 = time.perf_counter()
        self.graph = GraphStore(KUZU_PATH)
        self.graph.build(DATA_DIR)
        report["graph_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        report["graph_counts"] = self.graph.counts

        self.build_report = report
        self.ready = True

    # -- hydration ---------------------------------------------------------

    def doc_by_rowid(self, rowid: int) -> dict[str, Any]:
        assert self.conn is not None
        row = self.conn.execute(
            "SELECT doc_rowid, id, kind, ref_id, title, body, meta FROM documents "
            "WHERE doc_rowid = ?",
            (rowid,),
        ).fetchone()
        return self._doc(row)

    @staticmethod
    def _doc(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "doc_rowid": row["doc_rowid"],
            "id": row["id"],
            "kind": row["kind"],
            "ref_id": row["ref_id"],
            "title": row["title"],
            "body": row["body"],
            "meta": json.loads(row["meta"]),
        }

    def player(self, player_id: str) -> dict[str, Any] | None:
        assert self.conn is not None
        row = self.conn.execute(
            "SELECT p.*, t.name AS team_name FROM players p "
            "JOIN teams t ON t.id = p.team_id WHERE p.id = ?",
            (player_id,),
        ).fetchone()
        return dict(row) if row else None

    def article(self, article_id: str) -> dict[str, Any] | None:
        assert self.conn is not None
        row = self.conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
        if not row:
            return None
        out = dict(row)
        for field in ("tags", "teams", "entities"):
            out[field] = json.loads(out[field])
        return out


index = ArenaIndex()
