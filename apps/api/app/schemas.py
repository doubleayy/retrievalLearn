"""Wire format between the API and the web app.

The response is deliberately verbose: this is a teaching tool, so every query
that ran, every score that was computed, and every ontology term that was
expanded is returned to the client rather than hidden.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

Mode = Literal["keyword", "semantic", "graph", "hybrid", "hybrid_ontology"]

MODES: list[str] = ["keyword", "semantic", "graph", "hybrid", "hybrid_ontology"]


class SearchRequest(BaseModel):
    query: str
    mode: Mode = "keyword"
    limit: int = 8


class ExecutedStep(BaseModel):
    """One concrete thing the engine did, with the query language it used."""

    label: str
    language: Literal["sql", "cypher", "python", "text", "json"]
    code: str
    params: dict[str, Any] = Field(default_factory=dict)
    engine: str
    row_count: int = 0
    latency_ms: float = 0.0
    note: str = ""
    error: str = ""
    # Raw tabular output, when the step produced one (graph modes).
    table: dict[str, Any] | None = None


class ResultItem(BaseModel):
    id: str
    kind: Literal["article", "player", "trade", "path"]
    title: str
    snippet: str = ""
    score: float = 0.0
    rank: int = 0
    score_breakdown: dict[str, Any] = Field(default_factory=dict)
    why: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class OntologyTrace(BaseModel):
    matched_phrases: list[dict[str, Any]] = Field(default_factory=list)
    expanded_classes: list[str] = Field(default_factory=list)
    expanded_synonyms: list[str] = Field(default_factory=list)
    sql_predicates: list[str] = Field(default_factory=list)
    derived_relations: list[str] = Field(default_factory=list)
    turtle: str = ""


class PlanInfo(BaseModel):
    model: str = ""
    interpretation: str = ""
    explanation: str = ""
    entities: list[dict[str, Any]] = Field(default_factory=list)
    keyword_query: str = ""
    semantic_query: str = ""
    cypher: str = ""
    sql_filter: str = ""
    ontology_terms: list[str] = Field(default_factory=list)
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cached: bool = False
    repaired: bool = False


class Explain(BaseModel):
    what_happened: str
    strengths: list[str] = Field(default_factory=list)
    limits: list[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    query: str
    mode: Mode
    plan: PlanInfo
    steps: list[ExecutedStep] = Field(default_factory=list)
    results: list[ResultItem] = Field(default_factory=list)
    ontology_trace: OntologyTrace | None = None
    fusion: dict[str, Any] | None = None
    explain: Explain
    timings: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
