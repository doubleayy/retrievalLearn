"""Ontology-driven query expansion.

This module is the entire difference between "hybrid" and "hybrid + ontology"
in this app. It is deliberately deterministic - no model call - so that the
expansion trace shown in the UI is exactly reproducible and can be read as a
proof rather than trusted as an opinion.

Given the user's raw question it produces:
  * the domain phrases that matched a class or property in the ontology,
  * the transitive closure of those classes,
  * a set of SQL predicates over `players`,
  * a Cypher statement assembled from the matched classes and relations,
  * a synonym bag used to widen the keyword and vector queries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .ontology import Ontology

PLAYER_COLUMNS = (
    "position", "age", "ppg", "rpg", "apg", "spg", "bpg", "fg3_pct",
    "salary_usd", "draft_year", "draft_pick", "height_in", "weight_lb",
    "college", "country", "team_id",
)

# Relations that make a two-hop "and also" question possible.
PLAYER_RELATIONS = {
    "conflictWith": "CONFLICT_WITH",
    "formerTeammateOf": "FORMER_TEAMMATE",
    "teammateOf": "TEAMMATE",
    "draftClassmateOf": "DRAFT_CLASSMATE",
}


@dataclass
class Expansion:
    matches: list[dict[str, Any]] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    properties: list[str] = field(default_factory=list)
    synonyms: list[str] = field(default_factory=list)
    sql_predicates: list[str] = field(default_factory=list)
    conflict_kinds: list[str] = field(default_factory=list)
    derived_relations: list[str] = field(default_factory=list)
    cypher: str = ""
    cypher_note: str = ""

    @property
    def is_empty(self) -> bool:
        return not self.matches


def sql_to_cypher_predicate(predicate: str, alias: str = "a") -> str:
    """Translate a SQLite predicate over `players` into Kuzu Cypher.

    Two mechanical changes: qualify bare column names with the node alias, and
    turn SQL's `IN ('a','b')` tuples into Cypher's `IN ['a','b']` lists.
    """
    out = predicate
    for col in PLAYER_COLUMNS:
        out = re.sub(rf"(?<![\w.]){col}\b", f"{alias}.{col}", out)
    out = re.sub(r"IN\s*\(([^)]*)\)", lambda m: f"IN [{m.group(1)}]", out, flags=re.IGNORECASE)
    out = out.replace(" IS NULL", " IS NULL")
    return out


def expand(query: str, onto: Ontology, extra_terms: list[str] | None = None) -> Expansion:
    text = query
    for term in extra_terms or []:
        if term.lower() not in text.lower():
            text = f"{text} {term}"

    exp = Expansion()
    exp.matches = onto.match(text)
    if not exp.matches:
        return exp

    class_ids = [m["resolved_to"] for m in exp.matches if m["kind"] == "class"]
    prop_ids = [m["resolved_to"] for m in exp.matches if m["kind"] == "property"]

    closure: set[str] = set()
    for cid in class_ids:
        closure |= onto.expand(cid)
    exp.classes = sorted(closure)
    exp.properties = sorted(set(prop_ids))
    exp.synonyms = onto.synonyms_for(closure)[:40]

    # Conflict subclasses become a value filter, not a text filter.
    conflict_classes = [c for c in closure if onto.is_conflict_class(c) and c != "Conflict"]
    exp.conflict_kinds = sorted(conflict_classes)

    # Structured predicates from the player-side classes.
    seen: set[str] = set()
    for cid in class_ids:
        pred = onto.sql_predicate_for(cid)
        if pred and pred not in seen:
            seen.add(pred)
            exp.sql_predicates.append(pred)

    exp.derived_relations = [
        pid for pid in exp.properties if onto.properties.get(pid, {}).get("derived")
    ]

    exp.cypher, exp.cypher_note = _build_cypher(exp, onto, prop_ids)
    return exp


def _build_cypher(exp: Expansion, onto: Ontology, prop_ids: list[str]) -> tuple[str, str]:
    """Assemble Cypher from the matched classes and relations.

    Nothing here is model-generated: the shape follows directly from how many
    relations the ontology recognised in the question.
    """
    rels = [PLAYER_RELATIONS[p] for p in prop_ids if p in PLAYER_RELATIONS]
    # Preserve order, drop duplicates.
    rels = list(dict.fromkeys(rels))
    where_a = [sql_to_cypher_predicate(p, "a") for p in exp.sql_predicates]

    if exp.conflict_kinds and "CONFLICT_WITH" not in rels:
        rels.insert(0, "CONFLICT_WITH")

    if not rels:
        if not where_a:
            return "", ""
        clause = "\n  AND ".join(where_a)
        return (
            f"MATCH (a:Player)\nWHERE {clause}\n"
            f"RETURN a.id AS id, a.name AS name, a.position AS position,\n"
            f"       a.team_id AS team, a.ppg AS ppg, a.fg3_pct AS fg3_pct\n"
            f"ORDER BY a.ppg DESC\nLIMIT 25",
            "No relation was recognised, so the ontology contributed a class "
            "restriction over players and nothing more.",
        )

    kind_filter = ""
    if exp.conflict_kinds and "CONFLICT_WITH" in rels:
        kinds = ", ".join(f"'{k}'" for k in exp.conflict_kinds)
        kind_filter = f"r0.kind IN [{kinds}]"

    if len(rels) >= 2:
        # Two-hop cycle: a is related to b one way, and b back to a the other.
        r0, r1 = rels[0], rels[1]
        conditions = where_a + ([kind_filter] if kind_filter else [])
        where = ("WHERE " + "\n  AND ".join(conditions) + "\n") if conditions else ""
        return (
            f"MATCH (a:Player)-[r0:{r0}]->(b:Player)-[r1:{r1}]->(a)\n"
            f"{where}"
            f"RETURN DISTINCT a.id AS id, a.name AS name, a.position AS position,\n"
            f"       b.name AS counterpart, r0.kind AS relation_detail\n"
            f"LIMIT 25",
            f"Two derived relations were recognised, so the query became a cycle: "
            f"a player linked to someone by {r0} who is linked back by {r1}. "
            f"Neither edge exists in any source file.",
        )

    r0 = rels[0]
    conditions = where_a + ([kind_filter] if kind_filter else [])
    where = ("WHERE " + "\n  AND ".join(conditions) + "\n") if conditions else ""
    detail = "r0.kind AS relation_detail" if r0 == "CONFLICT_WITH" else "r0.team_id AS via_team"
    return (
        f"MATCH (a:Player)-[r0:{r0}]->(b:Player)\n"
        f"{where}"
        f"RETURN DISTINCT a.id AS id, a.name AS name, a.position AS position,\n"
        f"       b.name AS counterpart, {detail}\n"
        f"LIMIT 25",
        f"One derived relation ({r0}) plus any class restrictions on the subject.",
    )


def widen_keyword(original: str, exp: Expansion, limit: int = 12) -> str:
    """Add ontology synonyms to an FTS5 expression as an OR group."""
    if not exp.synonyms:
        return original
    terms = []
    for syn in exp.synonyms[:limit]:
        clean = re.sub(r"[^a-zA-Z0-9 -]", "", syn).strip()
        if not clean:
            continue
        # Always quote. FTS5 parses a bare hyphen as a column separator, so
        # `seven-footer` becomes "no such column: footer".
        terms.append(f'"{clean}"')
    if not terms:
        return original
    group = " OR ".join(dict.fromkeys(terms))
    return f"({original}) OR ({group})" if original.strip() else group


def widen_semantic(original: str, exp: Expansion, limit: int = 8) -> str:
    if not exp.synonyms:
        return original
    extra = ", ".join(exp.synonyms[:limit])
    return f"{original}. Related concepts: {extra}"
