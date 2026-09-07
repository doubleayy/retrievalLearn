"""The query planner: natural language in, executable query languages out.

One Claude call produces the plan for *every* mode at once - an FTS5 match
expression, a rewritten string to embed, a Cypher statement and a SQL filter.
Generating all four is deliberate: it costs one call instead of five, and it
lets the UI show what the other modes would have done with the same question.

The system prompt is long and completely static, so it is cached. Watch
`cache_read_tokens` in the response to confirm.
"""

from __future__ import annotations

import json
import re
import time
from collections import OrderedDict
from typing import Any

import anthropic

from .config import (
    ANTHROPIC_API_KEY,
    PLAN_CACHE_SIZE,
    PLANNER_EFFORT,
    PLANNER_MAX_TOKENS,
    PLANNER_MODEL,
)
from .ontology import get_ontology
from .stores.graph import SCHEMA_FOR_PROMPT

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "interpretation": {
            "type": "string",
            "description": "One sentence, plain English, restating what the user is asking for.",
        },
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "kind": {
                        "type": "string",
                        "enum": ["player", "team", "position", "metric", "event", "other"],
                    },
                    "resolved_id": {"type": "string"},
                },
                "required": ["text", "kind", "resolved_id"],
                "additionalProperties": False,
            },
        },
        "keyword_query": {"type": "string"},
        "semantic_query": {"type": "string"},
        "cypher": {"type": "string"},
        "sql_filter": {"type": "string"},
        "ontology_terms": {"type": "array", "items": {"type": "string"}},
        "explanation": {"type": "string"},
    },
    "required": [
        "interpretation",
        "entities",
        "keyword_query",
        "semantic_query",
        "cypher",
        "sql_filter",
        "ontology_terms",
        "explanation",
    ],
    "additionalProperties": False,
}


def _build_system_prompt() -> str:
    onto = get_ontology()
    defined = "\n".join(
        f"  {c['id']:<18} = {c.get('equivalent_to', '')}   (synonyms: "
        f"{', '.join(c.get('synonyms', [])[:5])})"
        for c in (onto.classes[cid] for cid in onto.defined_class_ids())
    )
    conflict_kinds = ", ".join(
        k for k in onto.conflict_kinds() if k != "Conflict"
    )
    return f"""You translate natural language questions about a basketball database into
four different query languages at once. You are the planning stage of a teaching tool
that shows beginners how keyword, semantic, graph and ontology-aware retrieval differ.

# The corpus
103 documents: 44 news articles, 38 player scouting profiles, 21 trade summaries.
Plus a structured players table and a property graph. The data is a snapshot of
roughly the 2023-24 season.

# 1. keyword_query -> SQLite FTS5 MATCH expression
Syntax you may use: bare terms, "quoted phrases", OR, AND, NOT, NEAR(a b, 5),
prefix* wildcards, and column filters like  title: durant.
Do NOT write the word MATCH, do not write SELECT, do not add quotes around the
whole expression. Keep it to the words a person would actually have typed, plus
obvious morphological variants. This mode is supposed to be literal - do not
enrich it with synonyms the user did not use. Its failures are the lesson.
Example: for "Draymond Green suspension" write:  draymond OR green AND suspend*

# 2. semantic_query -> a string to embed
Rewrite the question as a short declarative sentence resembling the passage you
hope to find, not as a question. Expand pronouns, drop stop-words, keep proper
nouns. This is what gets embedded by BAAI/bge-small-en-v1.5.
Example: for "who has beef with their old teammates?" write:
"players involved in disputes and altercations with former teammates"

# 3. cypher -> a read-only Kuzu Cypher statement
{SCHEMA_FOR_PROMPT}

Kuzu Cypher rules:
- Supported: MATCH, OPTIONAL MATCH, WHERE, RETURN, DISTINCT, ORDER BY, LIMIT,
  count(), collect(), lower(), contains(a, b), list literals with square brackets.
- List membership is  x IN ['PF', 'C']  with square brackets, never curly braces.
- Never write CREATE, MERGE, SET, DELETE or DROP. Read-only only.
- Always end with a LIMIT of 25 or fewer.
- Whenever the answer is a set of players or articles, RETURN a column literally
  named `id` (the Player.id or Article.id) alongside human-readable columns, so
  the application can hydrate full records. Alias it: RETURN a.id AS id, a.name AS name
- Player-to-player edges exist in both directions, so match one direction only or
  you will get every pair twice. Use DISTINCT.
- If the question cannot be expressed as a graph traversal at all, return an empty
  string for cypher rather than inventing a query.

# 4. sql_filter -> a WHERE fragment over the `players` table
Columns: id, name, team_id, position, height_in, weight_lb, age, ppg, rpg, apg,
spg, bpg, fg3_pct, salary_usd, draft_year, draft_pick, college, country.
Return only the boolean expression, with no WHERE keyword. Empty string if the
question implies no structured filter on players.
Example: for "young bigs who shoot" write:  age <= 24 AND position IN ('PF','C') AND fg3_pct >= 0.35

# 5. ontology_terms
List the surface phrases in the user's question that are domain concepts rather
than literal strings - the phrases a reasoner should expand. Copy them verbatim
from the question. These defined classes exist:
{defined}
Conflict has these subclasses: {conflict_kinds}.
Relations that are DERIVED (they exist in no source file): formerTeammateOf,
teammateOf, conflictWith, draftClassmateOf, divisionRivalOf.

# Style
`explanation` is one sentence for a beginner about why these queries differ.
Never invent player names, team codes or statistics. If the question is off-topic
or unanswerable from this corpus, still return valid queries that will simply
return nothing, and say so in `interpretation`."""


class PlannerError(RuntimeError):
    pass


def supports_effort(model: str) -> bool:
    """Whether `output_config.effort` is accepted by this model.

    Effort is rejected with a 400 on Haiku 4.5 and the other pre-4.6 models, so
    sending it unconditionally makes PLANNER_MODEL=claude-haiku-4-5 fail every
    query. Gating it here keeps the model a pure environment-variable change.
    """
    return not ("haiku" in model or "-4-5" in model)


def build_output_config(model: str, schema: dict | None) -> dict:
    config: dict[str, Any] = {}
    if schema is not None:
        config["format"] = {"type": "json_schema", "schema": schema}
    if PLANNER_EFFORT and supports_effort(model):
        config["effort"] = PLANNER_EFFORT
    return config


class Planner:
    def __init__(self) -> None:
        self._client: anthropic.Anthropic | None = None
        self._system: str | None = None
        self._cache: OrderedDict[str, dict] = OrderedDict()

    @property
    def enabled(self) -> bool:
        return bool(ANTHROPIC_API_KEY)

    @property
    def client(self) -> anthropic.Anthropic:
        if self._client is None:
            if not ANTHROPIC_API_KEY:
                raise PlannerError(
                    "ANTHROPIC_API_KEY is not set. The planner turns your question into "
                    "SQL and Cypher, so the API needs a key to answer anything."
                )
            self._client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=60.0)
        return self._client

    @property
    def system(self) -> str:
        if self._system is None:
            self._system = _build_system_prompt()
        return self._system

    def plan(self, query: str) -> dict:
        key = query.strip().lower()
        if key in self._cache:
            cached = dict(self._cache[key])
            cached["cached"] = True
            cached["latency_ms"] = 0.0
            self._cache.move_to_end(key)
            return cached

        started = time.perf_counter()
        response = self.client.messages.create(
            model=PLANNER_MODEL,
            max_tokens=PLANNER_MAX_TOKENS,
            system=[
                {
                    "type": "text",
                    "text": self.system,
                    "cache_control": {"type": "ephemeral", "ttl": "1h"},
                }
            ],
            messages=[{"role": "user", "content": query}],
            output_config=build_output_config(PLANNER_MODEL, PLAN_SCHEMA),
        )
        if response.stop_reason == "refusal":
            raise PlannerError(
                "The planner declined to answer that question. Try rephrasing it "
                "around the basketball data."
            )

        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            plan = json.loads(text)
        except json.JSONDecodeError as exc:  # pragma: no cover - schema makes this rare
            raise PlannerError(f"Planner returned unparseable JSON: {exc}") from exc

        plan["model"] = PLANNER_MODEL
        plan["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
        plan["input_tokens"] = response.usage.input_tokens
        plan["output_tokens"] = response.usage.output_tokens
        plan["cache_read_tokens"] = getattr(response.usage, "cache_read_input_tokens", 0) or 0
        # A first call WRITES the cache: reads are 0 but creation is ~1,550.
        # Reporting only reads makes a working cache look broken.
        plan["cache_write_tokens"] = (
            getattr(response.usage, "cache_creation_input_tokens", 0) or 0
        )
        plan["cached"] = False
        plan["repaired"] = False
        plan["cypher"] = _strip_fences(plan.get("cypher", ""))

        self._cache[key] = plan
        while len(self._cache) > PLAN_CACHE_SIZE:
            self._cache.popitem(last=False)
        return dict(plan)

    def repair_cypher(self, query: str, cypher: str, error: str) -> str:
        """One retry when Kuzu rejects the generated Cypher."""
        response = self.client.messages.create(
            model=PLANNER_MODEL,
            max_tokens=1500,
            system=[
                {
                    "type": "text",
                    "text": self.system,
                    "cache_control": {"type": "ephemeral", "ttl": "1h"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"This Cypher failed against Kuzu.\n\n"
                        f"Original question: {query}\n\n"
                        f"Query:\n{cypher}\n\n"
                        f"Error:\n{error}\n\n"
                        f"Return corrected Cypher only, no prose and no code fences."
                    ),
                }
            ],
            output_config=build_output_config(PLANNER_MODEL, None),
        )
        text = next((b.text for b in response.content if b.type == "text"), "")
        return _strip_fences(text)


def _strip_fences(text: str) -> str:
    text = text.strip()
    fenced = re.match(r"^```[a-zA-Z]*\n(.*)\n```$", text, re.DOTALL)
    if fenced:
        return fenced.group(1).strip()
    return text


planner = Planner()
