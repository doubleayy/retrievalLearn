"""Retrieval Arena API.

Five retrieval modes over one corpus, each returning not just results but the
query language it used to get them.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from .catalog import EXAMPLES, build_catalog, ontology_payload
from .config import (
    CORS_ORIGIN_REGEX,
    CORS_ORIGINS,
    DATA_DIR,
    DEFAULT_LIMIT,
    MAX_LIMIT,
    MAX_QUERY_CHARS,
    PLANNER_MODEL,
    RATE_LIMIT_PER_MIN,
)
from .index import index
from .planner import PlannerError, planner
from .retrievers import graphsearch, hybrid, keyword, semantic
from .schemas import Explain, PlanInfo, SearchRequest, SearchResponse

MODE_INFO: list[dict[str, Any]] = [
    {
        "id": "keyword",
        "name": "Keyword search",
        "tagline": "Exact terms, BM25, an inverted index",
        "language": "SQL (SQLite FTS5)",
        "one_liner": "Finds documents containing the words you typed. Nothing else.",
    },
    {
        "id": "semantic",
        "name": "Semantic search",
        "tagline": "Dense vectors, cosine similarity",
        "language": "SQL (sqlite-vec)",
        "one_liner": "Finds documents that mean something similar, whatever words they use.",
    },
    {
        "id": "graph",
        "name": "Graph search",
        "tagline": "Pattern matching over entities and relationships",
        "language": "Cypher (Kuzu)",
        "one_liner": "Answers questions about how things connect, not what they say.",
    },
    {
        "id": "hybrid",
        "name": "Hybrid search",
        "tagline": "All three legs, fused with RRF",
        "language": "SQL + Cypher",
        "one_liner": "Runs keyword, vector and graph together and merges the rankings.",
    },
    {
        "id": "hybrid_ontology",
        "name": "Hybrid + ontology",
        "tagline": "Hybrid, but the domain is modelled first",
        "language": "SQL + Cypher + OWL-lite",
        "one_liner": "Resolves your words to domain classes before retrieving anything.",
    },
]

_hits: dict[str, deque] = defaultdict(deque)


@asynccontextmanager
async def lifespan(app: FastAPI):
    started = time.perf_counter()
    index.build()
    print(
        f"[arena] index ready in {time.perf_counter() - started:.1f}s "
        f"({index.build_report.get('vector_engine')})"
    )
    yield


app = FastAPI(title="Retrieval Arena API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=CORS_ORIGIN_REGEX,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def _rate_limit(request: Request) -> None:
    ip = (request.headers.get("x-forwarded-for", "") or "").split(",")[0].strip()
    ip = ip or (request.client.host if request.client else "unknown")
    now = time.time()
    bucket = _hits[ip]
    while bucket and now - bucket[0] > 60:
        bucket.popleft()
    if len(bucket) >= RATE_LIMIT_PER_MIN:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit is {RATE_LIMIT_PER_MIN} queries per minute. Try again shortly.",
        )
    bucket.append(now)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": index.ready,
        "planner_model": PLANNER_MODEL,
        "planner_configured": planner.enabled,
        "build": index.build_report,
    }


@app.get("/api/modes")
def modes() -> dict[str, Any]:
    return {"modes": MODE_INFO}


@app.get("/api/examples")
def examples() -> dict[str, Any]:
    return {"examples": EXAMPLES}


@app.get("/api/catalog")
def catalog() -> dict[str, Any]:
    if not index.ready:
        raise HTTPException(503, "Index still building.")
    return build_catalog(index)


@app.get("/api/ontology")
def ontology() -> dict[str, Any]:
    if not index.ready:
        raise HTTPException(503, "Index still building.")
    return ontology_payload(index)


@app.get("/api/eval")
def evaluation() -> dict[str, Any]:
    """The pre-run evaluation report.

    Generated offline by `python -m app.evaluation.runner` and served verbatim.
    Running it per request would mean 60 retrievals and, with a live planner,
    12 model calls - and would give two visitors two different reports.
    """
    report = _eval_report()
    if report is None:
        raise HTTPException(
            503,
            "No evaluation report has been generated. Run "
            "`python -m app.evaluation.runner` in apps/api to build one.",
        )
    return report


@lru_cache(maxsize=1)
def _eval_report() -> dict[str, Any] | None:
    path = DATA_DIR / "eval_report.json"
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


@app.post("/api/search", response_model=SearchResponse)
def search(req: SearchRequest, request: Request) -> SearchResponse:
    if not index.ready:
        raise HTTPException(503, "Index still building. Try again in a few seconds.")
    query = req.query.strip()
    if not query:
        raise HTTPException(400, "Empty query.")
    if len(query) > MAX_QUERY_CHARS:
        raise HTTPException(400, f"Query is limited to {MAX_QUERY_CHARS} characters.")
    _rate_limit(request)

    limit = max(1, min(req.limit or DEFAULT_LIMIT, MAX_LIMIT))
    total_started = time.perf_counter()

    try:
        plan = planner.plan(query)
    except PlannerError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - surface upstream failures verbatim
        raise HTTPException(status_code=502, detail=f"Planner call failed: {exc}") from exc

    retrieve_started = time.perf_counter()
    warnings: list[str] = []
    fusion = None
    trace = None
    repaired = False

    if req.mode == "keyword":
        step, results, warn = keyword.run(index, plan["keyword_query"], limit)
        steps, explain = [step], keyword.EXPLAIN
        warnings += warn
    elif req.mode == "semantic":
        steps, results, warn = semantic.run(index, plan["semantic_query"], limit)
        explain = semantic.EXPLAIN
        warnings += warn
    elif req.mode == "graph":
        steps, results, warn, repaired = graphsearch.run(
            index, plan["cypher"], limit, repair=planner.repair_cypher, question=query
        )
        explain = graphsearch.EXPLAIN
        warnings += warn
    else:
        use_ontology = req.mode == "hybrid_ontology"
        steps, results, fusion, trace, warn, repaired = hybrid.run(
            index,
            plan,
            limit,
            use_ontology=use_ontology,
            question=query,
            repair=planner.repair_cypher,
        )
        explain = hybrid.EXPLAIN_ONTOLOGY if use_ontology else hybrid.EXPLAIN_HYBRID
        warnings += warn

    retrieve_ms = round((time.perf_counter() - retrieve_started) * 1000, 1)

    if not results and not any(s.error for s in steps):
        warnings.append(
            "Zero results. For keyword and graph modes that is a real answer; for "
            "semantic mode it usually means the index is empty."
        )

    return SearchResponse(
        query=query,
        mode=req.mode,
        plan=PlanInfo(
            model=plan.get("model", PLANNER_MODEL),
            interpretation=plan.get("interpretation", ""),
            explanation=plan.get("explanation", ""),
            entities=plan.get("entities", []),
            keyword_query=plan.get("keyword_query", ""),
            semantic_query=plan.get("semantic_query", ""),
            cypher=plan.get("cypher", ""),
            sql_filter=plan.get("sql_filter", ""),
            ontology_terms=plan.get("ontology_terms", []),
            latency_ms=plan.get("latency_ms", 0.0),
            input_tokens=plan.get("input_tokens", 0),
            output_tokens=plan.get("output_tokens", 0),
            cache_read_tokens=plan.get("cache_read_tokens", 0),
            cache_write_tokens=plan.get("cache_write_tokens", 0),
            cached=plan.get("cached", False),
            repaired=repaired,
        ),
        steps=steps,
        results=results,
        ontology_trace=trace,
        fusion=fusion,
        explain=Explain(**explain),
        timings={
            "plan_ms": plan.get("latency_ms", 0.0),
            "retrieve_ms": retrieve_ms,
            "total_ms": round((time.perf_counter() - total_started) * 1000, 1),
        },
        warnings=warnings,
    )
