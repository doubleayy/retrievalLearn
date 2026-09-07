"""The data catalog and the curated example queries.

The catalog exists so that people can see what is actually in the box before
they start querying it - retrieval results are meaningless if you do not know
the corpus.
"""

from __future__ import annotations

import json
from typing import Any

from .index import ArenaIndex

DATASETS: list[dict[str, Any]] = [
    {
        "id": "players",
        "name": "Player registry",
        "shape": "structured",
        "table": "players",
        "grain": "one row per active player",
        "description": (
            "A snapshot of 38 players across 12 active rosters with per-game "
            "production, physicals, contract value and draft provenance."
        ),
        "columns": [
            ["id", "TEXT", "slug primary key, e.g. draymond-green"],
            ["name", "TEXT", "display name"],
            ["team_id", "TEXT", "FK to teams"],
            ["position", "TEXT", "PG | SG | SF | PF | C"],
            ["height_in", "INTEGER", "inches"],
            ["weight_lb", "INTEGER", "pounds"],
            ["age", "INTEGER", "years"],
            ["ppg / rpg / apg / spg / bpg", "REAL", "per-game production"],
            ["fg3_pct", "REAL", "three-point percentage, 0-1"],
            ["salary_usd", "INTEGER", "annual salary"],
            ["draft_year", "INTEGER", "year drafted"],
            ["draft_pick", "INTEGER", "overall pick, NULL if undrafted"],
            ["college", "TEXT", "college or overseas club"],
            ["country", "TEXT", "nationality"],
            ["bio", "TEXT", "a short scouting paragraph, also indexed as a document"],
        ],
        "visible_to": ["keyword", "semantic", "graph", "hybrid", "hybrid_ontology"],
        "note": (
            "The numeric columns are where keyword and semantic search fall over. "
            "'Who shoots above 38 percent' is trivial in SQL and hopeless in an "
            "inverted index."
        ),
    },
    {
        "id": "teams",
        "name": "Teams",
        "shape": "structured",
        "table": "teams",
        "grain": "one row per franchise",
        "description": (
            "25 franchises including historical ones needed to reconstruct player "
            "movement. Only 12 carry a current roster in this dataset."
        ),
        "columns": [
            ["id", "TEXT", "three-letter code, e.g. GSW"],
            ["name / city / arena", "TEXT", "identity"],
            ["conference", "TEXT", "East | West"],
            ["division", "TEXT", "used to derive DIVISION_RIVAL edges"],
            ["has_current_roster", "INTEGER", "1 if players in this dataset play here"],
        ],
        "visible_to": ["graph", "hybrid", "hybrid_ontology"],
        "note": "Division rivalry is not stored - it is derived from the division column.",
    },
    {
        "id": "stints",
        "name": "Roster stints",
        "shape": "structured / temporal",
        "table": "stints",
        "grain": "one row per player per continuous spell at a team",
        "description": (
            "69 season ranges spanning 2008-2025. This is the least glamorous table "
            "and the most important one: it is what makes 'former teammate' computable."
        ),
        "columns": [
            ["player_id", "TEXT", "FK to players"],
            ["team_id", "TEXT", "FK to teams"],
            ["from_season", "INTEGER", "first season, by ending year"],
            ["to_season", "INTEGER", "last season, by ending year"],
        ],
        "visible_to": ["graph", "hybrid", "hybrid_ontology"],
        "note": (
            "Overlapping ranges on the same team produce the 46 FORMER_TEAMMATE "
            "edges. No file in this repository contains that relationship."
        ),
    },
    {
        "id": "trades",
        "name": "Trade window graph",
        "shape": "graph / event",
        "table": "trades + trade_legs + trade_picks",
        "grain": "one trade, with player legs and draft-pick legs",
        "description": (
            "21 transactions from 2016-2024 including sign-and-trades and free agency "
            "moves, with 29 draft picks and their protections tracked separately."
        ),
        "columns": [
            ["trades.id / date / window / type", "TEXT", "the transaction"],
            ["trade_legs.player_id, from_team, to_team", "TEXT", "who moved where"],
            ["trade_picks.year, round, protection", "MIXED", "the asset ledger"],
        ],
        "visible_to": ["keyword", "semantic", "graph", "hybrid", "hybrid_ontology"],
        "note": (
            "Pick flows are edges, not prose. 'Which team owes the most unprotected "
            "firsts' is answerable only here."
        ),
    },
    {
        "id": "news",
        "name": "News and beef corpus",
        "shape": "unstructured text",
        "table": "articles",
        "grain": "one row per article",
        "description": (
            "44 short articles: 16 describe a conflict event, 6 are deliberate "
            "retrieval traps, and the rest are analysis, transactions and features. "
            "Written for this demo as neutral summaries of publicly reported events; "
            "no quotes are invented and no article is a real published piece."
        ),
        "columns": [
            ["id / title / body", "TEXT", "the document"],
            ["published_at", "TEXT", "ISO date"],
            ["source_type", "TEXT", "beat_report | feature | analysis | transaction_wire | lifestyle"],
            ["entities", "JSON", "player ids mentioned"],
            ["conflict_kind", "TEXT", "ontology class, NULL for non-conflict articles"],
            ["retrieval_note", "TEXT", "why this document is in the corpus, pedagogically"],
        ],
        "visible_to": ["keyword", "semantic", "graph", "hybrid", "hybrid_ontology"],
        "note": (
            "The traps are the point. Three articles contain the word 'beef' and "
            "describe food or weight training. Several describe real disputes without "
            "using any conflict vocabulary at all."
        ),
    },
    {
        "id": "conflict_edges",
        "name": "Derived conflict edges",
        "shape": "derived graph",
        "table": "conflict_edges",
        "grain": "one row per ordered player pair per conflict event",
        "description": (
            "20 edges materialised from the articles by ontology rule r3: two players "
            "named in the same conflict event are in conflict."
        ),
        "columns": [
            ["player_a / player_b", "TEXT", "the pair, stored in both directions"],
            ["kind", "TEXT", "the Conflict subclass"],
            ["severity", "TEXT", "low | medium | high"],
            ["article_id", "TEXT", "provenance"],
        ],
        "visible_to": ["graph", "hybrid", "hybrid_ontology"],
        "note": "Every edge carries the article it came from, so results stay auditable.",
    },
    {
        "id": "documents",
        "name": "Unified document index",
        "shape": "text index",
        "table": "documents + documents_fts + doc_vectors",
        "grain": "one row per searchable document",
        "description": (
            "103 documents: 44 articles, 38 player bios, 21 trade summaries. Keyword "
            "and vector search see exactly this set, so the comparison between them "
            "is fair."
        ),
        "columns": [
            ["id", "TEXT", "article:n01 | player:ja-morant | trade:trade-kd-phx-2023"],
            ["title / body", "TEXT", "indexed by FTS5 with title weighted 2x"],
            ["embedding", "float[384]", "BAAI/bge-small-en-v1.5, cosine metric"],
        ],
        "visible_to": ["keyword", "semantic", "hybrid", "hybrid_ontology"],
        "note": "Documents are not chunked: every document is short enough to embed whole.",
    },
    {
        "id": "ontology",
        "name": "Domain ontology",
        "shape": "OWL-lite",
        "table": "data/ontology.json",
        "grain": "classes, properties and rules",
        "description": (
            "24 asserted classes, 10 defined classes with equivalence axioms, 11 object "
            "properties and 5 inference rules. Consulted only by the hybrid + ontology mode."
        ),
        "columns": [
            ["classes", "-", "taxonomy with synonyms, e.g. Center ← 'the five', 'seven-footer'"],
            ["defined_classes", "-", "BigMan ≡ PowerForward ⊔ Center; Sniper ≡ fg3_pct ≥ 0.38"],
            ["object_properties", "-", "which Cypher edge each relation maps to"],
            ["rules", "-", "how the derived edges are computed"],
        ],
        "visible_to": ["hybrid_ontology"],
        "note": "Rendered as Turtle in the ontology tab so the axioms are readable.",
    },
]


EXAMPLES: list[dict[str, Any]] = [
    {
        "id": "beef-trap",
        "query": "which players have beef with each other?",
        "headline": "The word trap",
        "lesson": (
            "Keyword search ranks a brisket article, a beef Wellington article and a "
            "weight-training article above the one real feud explainer. Semantic search "
            "drops all three. Ontology mode expands 'beef' to seven conflict subclasses "
            "and returns the actual pairs."
        ),
        "try_modes": ["keyword", "semantic", "hybrid_ontology"],
    },
    {
        "id": "big-men-beef",
        "query": "which big men have beef with a former teammate?",
        "headline": "The one only the ontology can answer",
        "lesson": (
            "No document contains the phrase 'big man' near a conflict. 'Big men' has "
            "to become position IN ('PF','C'), 'beef' has to become a class hierarchy, "
            "and 'former teammate' has to become an edge derived from overlapping "
            "season ranges. Keyword and semantic both fail; ontology returns four correct pairs."
        ),
        "try_modes": ["keyword", "semantic", "hybrid", "hybrid_ontology"],
    },
    {
        "id": "bad-blood",
        "query": "who has bad blood with their old teammates?",
        "headline": "Paraphrase",
        "lesson": (
            "The corpus mostly says 'rift', 'altercation' and 'confrontation'. Keyword "
            "search for 'bad blood' finds a 1980s documentary and nothing else. Vectors "
            "find the real stories."
        ),
        "try_modes": ["keyword", "semantic"],
    },
    {
        "id": "snipers",
        "query": "which snipers are on max contracts?",
        "headline": "Thresholds are not vocabulary",
        "lesson": (
            "'Sniper' appears in no document. It is a defined class: fg3_pct >= 0.38. "
            "'Max contract' is salary_usd >= 35000000. Text retrieval cannot express "
            "either, so it returns articles about shooting instead of a list of players."
        ),
        "try_modes": ["semantic", "hybrid_ontology"],
    },
    {
        "id": "draymond-suspension",
        "query": "Draymond Green suspension",
        "headline": "Where keyword search wins",
        "lesson": (
            "A precise name and a precise noun. BM25 nails it in under a millisecond "
            "with no model call. The vector leg adds noise here, not signal."
        ),
        "try_modes": ["keyword", "semantic"],
    },
    {
        "id": "traded-twice",
        "query": "which players have been traded more than once?",
        "headline": "Counting is not searching",
        "lesson": (
            "No document states this. It requires counting edges per node. Text search "
            "returns an article that happens to mention a player being traded twice - "
            "which is not the same as the answer."
        ),
        "try_modes": ["semantic", "graph"],
    },
    {
        "id": "unprotected-picks",
        "query": "who owes the most unprotected first round picks?",
        "headline": "The ledger lives in edges",
        "lesson": (
            "There is one summary article about this, so semantic search looks like it "
            "worked. The graph gives you the actual counts, which do not match the "
            "article's framing."
        ),
        "try_modes": ["semantic", "graph"],
    },
    {
        "id": "absence",
        "query": "players with no conflict history",
        "headline": "Negation",
        "lesson": (
            "Embeddings cannot represent 'not'. The vector leg returns the most "
            "conflict-heavy articles in the corpus, including one whose whole point is "
            "the absence of open conflict. Only a graph traversal can express absence."
        ),
        "try_modes": ["semantic", "graph"],
    },
    {
        "id": "kentucky",
        "query": "which players went to Kentucky?",
        "headline": "A structured question wearing a text costume",
        "lesson": (
            "There is one article about the Kentucky pipeline, and text search finds it. "
            "But the article names six players and the database contains six - a "
            "coincidence that will not hold when your corpus grows."
        ),
        "try_modes": ["keyword", "graph"],
    },
    {
        "id": "rim-protectors",
        "query": "rim protectors who shoot threes",
        "headline": "Two defined classes at once",
        "lesson": (
            "'Rim protector' is bpg >= 1.5 and 'shoots threes' is a percentage "
            "threshold. Semantic search returns the article titled 'Rim protection is "
            "still the cheapest defense you can buy', which is on topic and useless."
        ),
        "try_modes": ["semantic", "hybrid_ontology"],
    },
]


def build_catalog(idx: ArenaIndex) -> dict[str, Any]:
    assert idx.conn is not None
    counts = idx.build_report.get("tables", {})
    out = []
    for dataset in DATASETS:
        entry = dict(dataset)
        entry["row_count"] = _count_for(dataset["id"], counts, idx)
        entry["sample"] = _sample(dataset["id"], idx)
        out.append(entry)
    return {
        "datasets": out,
        "totals": counts,
        "graph": idx.build_report.get("graph_counts", {}),
        "vector_engine": idx.build_report.get("vector_engine", ""),
        "build_ms": {
            k: v for k, v in idx.build_report.items() if k.endswith("_ms")
        },
        "disclaimer": (
            "Seed data is a hand-authored teaching corpus. Player statistics are "
            "approximate public-record values for roughly the 2023-24 season. The news "
            "articles are original neutral summaries of publicly reported events written "
            "for this demo - they are not reproductions of real articles and contain no "
            "invented quotes. Six articles are deliberate retrieval traps."
        ),
    }


def _count_for(dataset_id: str, counts: dict[str, int], idx: ArenaIndex) -> int:
    mapping = {
        "players": "players",
        "teams": "teams",
        "stints": "stints",
        "trades": "trades",
        "news": "articles",
        "conflict_edges": "conflict_edges",
        "documents": "documents",
    }
    if dataset_id == "ontology":
        return len(idx.onto.classes)
    return counts.get(mapping.get(dataset_id, ""), 0)


def _sample(dataset_id: str, idx: ArenaIndex) -> list[dict[str, Any]]:
    assert idx.conn is not None
    queries = {
        "players": "SELECT id, name, team_id, position, age, ppg, fg3_pct, salary_usd, "
                   "draft_pick FROM players ORDER BY ppg DESC LIMIT 5",
        "teams": "SELECT id, name, conference, division, has_current_roster FROM teams LIMIT 5",
        "stints": "SELECT player_id, team_id, from_season, to_season FROM stints "
                  "ORDER BY player_id LIMIT 5",
        "trades": "SELECT id, date, window, type, summary FROM trades ORDER BY date DESC LIMIT 4",
        "news": "SELECT id, title, published_at, source_type, conflict_kind, retrieval_note "
                "FROM articles LIMIT 5",
        "conflict_edges": "SELECT player_a, player_b, kind, severity, article_id "
                          "FROM conflict_edges LIMIT 5",
        "documents": "SELECT id, kind, title FROM documents LIMIT 5",
    }
    if dataset_id == "ontology":
        return [
            {
                "class": c["id"],
                "equivalent_to": c.get("equivalent_to", ""),
                "sql_predicate": c.get("sql_predicate", ""),
                "synonyms": ", ".join(c.get("synonyms", [])[:4]),
            }
            for c in (idx.onto.classes[cid] for cid in idx.onto.defined_class_ids()[:5])
        ]
    sql = queries.get(dataset_id)
    if not sql:
        return []
    return [dict(r) for r in idx.conn.execute(sql).fetchall()]


def ontology_payload(idx: ArenaIndex) -> dict[str, Any]:
    onto = idx.onto
    assert idx.conn is not None
    members: dict[str, list[str]] = {}
    for cid in onto.defined_class_ids():
        pred = onto.sql_predicate_for(cid)
        if not pred:
            continue
        rows = idx.conn.execute(
            f"SELECT name FROM players WHERE {pred} ORDER BY name"  # noqa: S608 - ontology-controlled
        ).fetchall()
        members[cid] = [r["name"] for r in rows]
    return {
        "iri": onto.iri,
        "prefix": onto.prefix,
        "description": onto.raw["description"],
        "classes": list(onto.classes.values()),
        "properties": list(onto.properties.values()),
        "rules": onto.rules,
        "showcase": onto.raw.get("showcase_expansions", []),
        "turtle": onto.to_turtle(),
        "defined_class_members": members,
        "conflict_kinds": [k for k in onto.conflict_kinds() if k != "Conflict"],
    }
