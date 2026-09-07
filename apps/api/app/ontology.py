"""A small OWL-lite reasoner.

Deliberately tiny and readable: subclass closure, synonym lookup, and the
mapping from a class to either a SQL predicate over `players` or a set of
conflict kinds. That is the entire difference between the "hybrid" mode and
the "hybrid + ontology" mode in this app, and it is worth being able to read
end to end.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from .config import DATA_DIR


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).strip()


class Ontology:
    def __init__(self, raw: dict[str, Any]):
        self.raw = raw
        self.iri: str = raw["iri"]
        self.prefix: str = raw["prefix"]

        self.classes: dict[str, dict] = {}
        for c in raw["classes"]:
            self.classes[c["id"]] = {**c, "defined": False}
        for c in raw["defined_classes"]:
            self.classes[c["id"]] = {**c, "defined": True}

        self.properties: dict[str, dict] = {p["id"]: p for p in raw["object_properties"]}
        self.rules: list[dict] = raw["rules"]

        # child -> parents, and the inverted parent -> children
        self._children: dict[str, set[str]] = {cid: set() for cid in self.classes}
        for cid, c in self.classes.items():
            for parent in c.get("parents", []):
                if parent in self._children:
                    self._children[parent].add(cid)
            # A union class is also "reachable" from its members for expansion
            # purposes, but we keep it out of the taxonomy tree so that
            # descendants_of("Player") does not explode.

        # synonym -> class id (longest phrases win at match time)
        self._syn_index: dict[str, str] = {}
        for cid, c in self.classes.items():
            for term in [c["label"], cid] + list(c.get("synonyms", [])):
                key = _norm(term)
                if key and key not in self._syn_index:
                    self._syn_index[key] = cid

        # synonym -> property id
        self._prop_index: dict[str, str] = {}
        for pid, p in self.properties.items():
            for term in [p["label"], pid] + list(p.get("synonyms", [])):
                key = _norm(term)
                if key and key not in self._prop_index:
                    self._prop_index[key] = pid

        self._max_phrase_words = max(
            (len(k.split()) for k in list(self._syn_index) + list(self._prop_index)),
            default=1,
        )

    # -- taxonomy ---------------------------------------------------------

    def descendants_of(self, class_id: str) -> set[str]:
        """Transitive subclass closure, inclusive of the class itself."""
        out: set[str] = set()
        stack = [class_id]
        while stack:
            cid = stack.pop()
            if cid in out or cid not in self.classes:
                continue
            out.add(cid)
            stack.extend(self._children.get(cid, ()))
        return out

    def expand(self, class_id: str) -> set[str]:
        """Closure plus union members, which is what a query actually needs."""
        out = self.descendants_of(class_id)
        for member in self.classes.get(class_id, {}).get("union_of", []):
            out |= self.descendants_of(member)
        return out

    def synonyms_for(self, class_ids: set[str]) -> list[str]:
        terms: list[str] = []
        for cid in sorted(class_ids):
            c = self.classes.get(cid)
            if not c:
                continue
            terms.append(c["label"])
            terms.extend(c.get("synonyms", []))
        seen: set[str] = set()
        out: list[str] = []
        for t in terms:
            k = t.lower()
            if k not in seen:
                seen.add(k)
                out.append(t)
        return out

    # -- mapping to storage ------------------------------------------------

    def sql_predicate_for(self, class_id: str) -> str | None:
        """The `players` WHERE fragment implied by a class, if any."""
        c = self.classes.get(class_id)
        if not c:
            return None
        if c.get("sql_predicate"):
            return c["sql_predicate"]
        codes = c.get("position_codes")
        if codes:
            joined = ",".join(f"'{code}'" for code in codes)
            return f"position IN ({joined})"
        # A non-leaf position class (Guard, Forward) resolves through its children.
        codes = sorted(
            {
                code
                for cid in self.descendants_of(class_id)
                for code in self.classes[cid].get("position_codes", [])
            }
        )
        if codes:
            joined = ",".join(f"'{code}'" for code in codes)
            return f"position IN ({joined})"
        return None

    def position_codes_for(self, class_ids: set[str]) -> list[str]:
        codes: set[str] = set()
        for cid in class_ids:
            codes |= set(self.classes.get(cid, {}).get("position_codes", []))
        return sorted(codes)

    def conflict_kinds(self) -> list[str]:
        return sorted(self.descendants_of("Conflict"))

    def is_conflict_class(self, class_id: str) -> bool:
        return class_id in self.descendants_of("Conflict")

    # -- phrase matching ---------------------------------------------------

    def match(self, text: str) -> list[dict[str, Any]]:
        """Longest-match scan of a natural language string against the ontology.

        Returns one entry per surface phrase found, with the class or property
        it resolved to. This is the visible "expansion trace" in the UI.
        """
        words = _norm(text).split()
        found: list[dict[str, Any]] = []
        i = 0
        while i < len(words):
            hit = None
            for span in range(min(self._max_phrase_words, len(words) - i), 0, -1):
                phrase = " ".join(words[i : i + span])
                if phrase in self._syn_index:
                    cid = self._syn_index[phrase]
                    hit = {
                        "phrase": phrase,
                        "resolved_to": cid,
                        "kind": "class",
                        "label": self.classes[cid]["label"],
                        "defined": self.classes[cid].get("defined", False),
                        "equivalent_to": self.classes[cid].get("equivalent_to", ""),
                        "span": span,
                    }
                    break
                if phrase in self._prop_index:
                    pid = self._prop_index[phrase]
                    hit = {
                        "phrase": phrase,
                        "resolved_to": pid,
                        "kind": "property",
                        "label": self.properties[pid]["label"],
                        "graph_rel": self.properties[pid].get("graph_rel", ""),
                        "derived": self.properties[pid].get("derived", False),
                        "span": span,
                    }
                    break
            if hit:
                found.append(hit)
                i += hit.pop("span")
            else:
                i += 1
        return found

    # -- classification ----------------------------------------------------

    def defined_class_ids(self) -> list[str]:
        return [cid for cid, c in self.classes.items() if c.get("defined")]

    # -- serialisation -----------------------------------------------------

    def to_turtle(self, only: set[str] | None = None) -> str:
        """Render the ontology (or a subset) as Turtle.

        Shown in the UI so people can see that "big man" really is a modelled
        class with an equivalence axiom, not a hardcoded synonym list.
        """
        lines = [
            f"@prefix {self.prefix}: <{self.iri}> .",
            "@prefix owl:   <http://www.w3.org/2002/07/owl#> .",
            "@prefix rdfs:  <http://www.w3.org/2000/01/rdf-schema#> .",
            "@prefix skos:  <http://www.w3.org/2004/02/skos/core#> .",
            "",
        ]
        p = self.prefix
        for cid, c in self.classes.items():
            if only is not None and cid not in only:
                continue
            lines.append(f"{p}:{cid} a owl:Class ;")
            lines.append(f'    rdfs:label "{c["label"]}" ;')
            for parent in c.get("parents", []):
                lines.append(f"    rdfs:subClassOf {p}:{parent} ;")
            if c.get("union_of"):
                members = " ".join(f"{p}:{m}" for m in c["union_of"])
                lines.append(f"    owl:equivalentClass [ owl:unionOf ( {members} ) ] ;")
            elif c.get("sql_predicate") and c.get("defined"):
                lines.append(f'    {p}:sqlPredicate "{c["sql_predicate"]}" ;')
            for syn in c.get("synonyms", [])[:8]:
                lines.append(f'    skos:altLabel "{syn}" ;')
            lines[-1] = lines[-1].rstrip(" ;") + " ."
            lines.append("")

        if only is None:
            for pid, prop in self.properties.items():
                kind = "owl:SymmetricProperty" if prop.get("symmetric") else "owl:ObjectProperty"
                lines.append(f"{p}:{pid} a {kind} ;")
                lines.append(f'    rdfs:label "{prop["label"]}" ;')
                lines.append(f"    rdfs:domain {p}:{prop['domain']} ;")
                lines.append(f"    rdfs:range {p}:{prop['range']} ;")
                lines[-1] = lines[-1].rstrip(" ;") + " ."
                lines.append("")
        return "\n".join(lines)

    def graph_schema_summary(self) -> str:
        """Compact schema description handed to Claude when it writes Cypher."""
        rels = [
            f"({p['domain']})-[:{p['graph_rel']}]->({p['range']})"
            for p in self.properties.values()
            if p.get("graph_rel")
        ]
        return "\n".join(rels)


@lru_cache(maxsize=1)
def get_ontology() -> Ontology:
    with open(DATA_DIR / "ontology.json", encoding="utf-8") as fh:
        return Ontology(json.load(fh))
