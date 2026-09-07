"""Kuzu: an embedded property graph that speaks real Cypher.

Every Cypher statement the UI shows is executed against this database. Five of
the eleven relationship types are *derived* at build time rather than read from
a file - that is the whole point of the graph mode.
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

import kuzu

from ..config import KUZU_BUFFER_POOL_MB, KUZU_MAX_DB_SIZE_MB, KUZU_MAX_THREADS

DDL = [
    """CREATE NODE TABLE Player(
        id STRING, name STRING, position STRING, team_id STRING,
        age INT64, height_in INT64, ppg DOUBLE, rpg DOUBLE, apg DOUBLE,
        bpg DOUBLE, fg3_pct DOUBLE, salary_usd INT64,
        draft_year INT64, draft_pick INT64, college STRING, country STRING,
        PRIMARY KEY (id))""",
    """CREATE NODE TABLE Team(
        id STRING, name STRING, city STRING, conference STRING, division STRING,
        PRIMARY KEY (id))""",
    """CREATE NODE TABLE Article(
        id STRING, title STRING, published_at STRING, source_type STRING,
        conflict_kind STRING, body STRING,
        PRIMARY KEY (id))""",
    """CREATE NODE TABLE Trade(
        id STRING, date STRING, window STRING, type STRING, summary STRING,
        PRIMARY KEY (id))""",
    "CREATE REL TABLE PLAYS_FOR(FROM Player TO Team)",
    "CREATE REL TABLE PLAYED_FOR(FROM Player TO Team, from_season INT64, to_season INT64)",
    "CREATE REL TABLE TEAMMATE(FROM Player TO Player, team_id STRING)",
    """CREATE REL TABLE FORMER_TEAMMATE(
        FROM Player TO Player, team_id STRING, from_season INT64, to_season INT64)""",
    """CREATE REL TABLE CONFLICT_WITH(
        FROM Player TO Player, kind STRING, severity STRING,
        article_id STRING, occurred STRING)""",
    "CREATE REL TABLE DRAFT_CLASSMATE(FROM Player TO Player, draft_year INT64)",
    "CREATE REL TABLE DIVISION_RIVAL(FROM Team TO Team, division STRING)",
    "CREATE REL TABLE MENTIONED_IN(FROM Player TO Article)",
    "CREATE REL TABLE INVOLVED_IN(FROM Player TO Trade, from_team STRING, to_team STRING)",
    "CREATE REL TABLE TRADE_FROM(FROM Trade TO Team)",
    "CREATE REL TABLE TRADE_TO(FROM Trade TO Team)",
]

SCHEMA_FOR_PROMPT = """NODES
  (:Player  {id, name, position, team_id, age, height_in, ppg, rpg, apg, bpg,
             fg3_pct, salary_usd, draft_year, draft_pick, college, country})
  (:Team    {id, name, city, conference, division})
  (:Article {id, title, published_at, source_type, conflict_kind, body})
  (:Trade   {id, date, window, type, summary})

RELATIONSHIPS  (all player-to-player edges are stored in BOTH directions)
  (:Player)-[:PLAYS_FOR]->(:Team)
  (:Player)-[:PLAYED_FOR {from_season, to_season}]->(:Team)
  (:Player)-[:TEAMMATE {team_id}]->(:Player)
  (:Player)-[:FORMER_TEAMMATE {team_id, from_season, to_season}]->(:Player)
  (:Player)-[:CONFLICT_WITH {kind, severity, article_id, occurred}]->(:Player)
  (:Player)-[:DRAFT_CLASSMATE {draft_year}]->(:Player)
  (:Team)-[:DIVISION_RIVAL {division}]->(:Team)
  (:Player)-[:MENTIONED_IN]->(:Article)
  (:Player)-[:INVOLVED_IN {from_team, to_team}]->(:Trade)
  (:Trade)-[:TRADE_FROM]->(:Team)
  (:Trade)-[:TRADE_TO]->(:Team)

VALUES
  Player.position    : 'PG' | 'SG' | 'SF' | 'PF' | 'C'
  CONFLICT_WITH.kind : 'OnCourtAltercation' | 'LockerRoomIncident' | 'PublicCallout'
                     | 'ContractDispute' | 'ConductSuspension' | 'RoleDispute' | 'Beef'
  Article.conflict_kind uses the same value set, or is NULL for non-conflict articles.
  Team.id is a three-letter code such as 'GSW', 'LAL', 'BOS'.
  Player.id is a slug such as 'draymond-green', 'kevin-durant'."""


class GraphStore:
    def __init__(self, path: Path):
        self.path = path
        self.db: Any = None
        self.conn: Any = None
        self.counts: dict[str, int] = {}

    def build(self, data_dir: Path) -> None:
        if self.path.exists():
            shutil.rmtree(self.path, ignore_errors=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Explicit limits are mandatory in a container: see KUZU_BUFFER_POOL_MB
        # in config.py for why the defaults get the process OOM-killed.
        self.db = kuzu.Database(
            str(self.path),
            buffer_pool_size=KUZU_BUFFER_POOL_MB * 1024 * 1024,
            max_db_size=KUZU_MAX_DB_SIZE_MB * 1024 * 1024,
            max_num_threads=KUZU_MAX_THREADS,
        )
        self.conn = kuzu.Connection(self.db)

        for stmt in DDL:
            self.conn.execute(stmt)

        def load(name: str) -> Any:
            with open(data_dir / f"{name}.json", encoding="utf-8") as fh:
                return json.load(fh)

        teams = load("teams")
        players = load("players")
        stints = load("stints")
        trades = load("trades")
        news = load("news")

        for t in teams:
            self._run(
                "CREATE (:Team {id:$id, name:$name, city:$city, conference:$conference, "
                "division:$division})",
                {k: t[k] for k in ("id", "name", "city", "conference", "division")},
            )
        for p in players:
            self._run(
                """CREATE (:Player {id:$id, name:$name, position:$position, team_id:$team_id,
                   age:$age, height_in:$height_in, ppg:$ppg, rpg:$rpg, apg:$apg, bpg:$bpg,
                   fg3_pct:$fg3_pct, salary_usd:$salary_usd, draft_year:$draft_year,
                   draft_pick:$draft_pick, college:$college, country:$country})""",
                {
                    k: p[k]
                    for k in (
                        "id", "name", "position", "team_id", "age", "height_in", "ppg",
                        "rpg", "apg", "bpg", "fg3_pct", "salary_usd", "draft_year",
                        "draft_pick", "college", "country",
                    )
                },
            )
        for a in news:
            self._run(
                """CREATE (:Article {id:$id, title:$title, published_at:$published_at,
                   source_type:$source_type, conflict_kind:$conflict_kind, body:$body})""",
                {
                    "id": a["id"],
                    "title": a["title"],
                    "published_at": a["published_at"],
                    "source_type": a["source_type"],
                    "conflict_kind": (a["conflict"] or {}).get("kind"),
                    "body": a["body"],
                },
            )
        for t in trades:
            self._run(
                """CREATE (:Trade {id:$id, date:$date, window:$window, type:$type,
                   summary:$summary})""",
                {k: t[k] for k in ("id", "date", "window", "type", "summary")},
            )

        # --- asserted edges ------------------------------------------------
        for p in players:
            self._run(
                "MATCH (a:Player {id:$p}), (b:Team {id:$t}) CREATE (a)-[:PLAYS_FOR]->(b)",
                {"p": p["id"], "t": p["team_id"]},
            )
        for s in stints:
            self._run(
                "MATCH (a:Player {id:$p}), (b:Team {id:$t}) "
                "CREATE (a)-[:PLAYED_FOR {from_season:$f, to_season:$ts}]->(b)",
                {"p": s["player_id"], "t": s["team_id"], "f": s["from_season"], "ts": s["to_season"]},
            )
        for a in news:
            for pid in a["entities"]:
                self._run(
                    "MATCH (p:Player {id:$p}), (x:Article {id:$a}) CREATE (p)-[:MENTIONED_IN]->(x)",
                    {"p": pid, "a": a["id"]},
                )
        for t in trades:
            for leg in t["legs"]:
                self._run(
                    "MATCH (p:Player {id:$p}), (x:Trade {id:$t}) "
                    "CREATE (p)-[:INVOLVED_IN {from_team:$f, to_team:$ts}]->(x)",
                    {"p": leg["player_id"], "t": t["id"], "f": leg["from_team"], "ts": leg["to_team"]},
                )
            for team_id in {leg["from_team"] for leg in t["legs"]}:
                self._run(
                    "MATCH (x:Trade {id:$t}), (m:Team {id:$m}) CREATE (x)-[:TRADE_FROM]->(m)",
                    {"t": t["id"], "m": team_id},
                )
            for team_id in {leg["to_team"] for leg in t["legs"]}:
                self._run(
                    "MATCH (x:Trade {id:$t}), (m:Team {id:$m}) CREATE (x)-[:TRADE_TO]->(m)",
                    {"t": t["id"], "m": team_id},
                )

        self._derive(players, stints, teams, news)
        self.counts = self._count()

    # -- derived edges (the ontology rules, materialised) -------------------

    def _derive(self, players: list, stints: list, teams: list, news: list) -> None:
        current = {p["id"]: p["team_id"] for p in players}

        # r1: teammateOf
        by_team: dict[str, list[str]] = defaultdict(list)
        for pid, tid in current.items():
            by_team[tid].append(pid)
        current_pairs: set[tuple[str, str]] = set()
        for tid, members in by_team.items():
            for i, a in enumerate(members):
                for b in members[i + 1 :]:
                    current_pairs.add((a, b))
                    current_pairs.add((b, a))
                    for x, y in ((a, b), (b, a)):
                        self._run(
                            "MATCH (p:Player {id:$a}), (q:Player {id:$b}) "
                            "CREATE (p)-[:TEAMMATE {team_id:$t}]->(q)",
                            {"a": x, "b": y, "t": tid},
                        )

        # r2: formerTeammateOf - overlapping stints on the same team, not
        # currently teammates. This edge exists in no source file.
        stints_by_team: dict[str, list[dict]] = defaultdict(list)
        for s in stints:
            stints_by_team[s["team_id"]].append(s)
        seen: set[tuple[str, str]] = set()
        for tid, rows in stints_by_team.items():
            for i, s1 in enumerate(rows):
                for s2 in rows[i + 1 :]:
                    if s1["player_id"] == s2["player_id"]:
                        continue
                    lo = max(s1["from_season"], s2["from_season"])
                    hi = min(s1["to_season"], s2["to_season"])
                    if lo > hi:
                        continue
                    pair = (s1["player_id"], s2["player_id"])
                    if pair in current_pairs or pair in seen:
                        continue
                    seen.add(pair)
                    seen.add(pair[::-1])
                    for x, y in (pair, pair[::-1]):
                        self._run(
                            "MATCH (p:Player {id:$a}), (q:Player {id:$b}) "
                            "CREATE (p)-[:FORMER_TEAMMATE "
                            "{team_id:$t, from_season:$f, to_season:$ts}]->(q)",
                            {"a": x, "b": y, "t": tid, "f": lo, "ts": hi},
                        )

        # r3: conflictWith
        for a in news:
            c = a.get("conflict")
            if not c:
                continue
            parts = c["participants"]
            for i, pa in enumerate(parts):
                for pb in parts[i + 1 :]:
                    for x, y in ((pa, pb), (pb, pa)):
                        self._run(
                            "MATCH (p:Player {id:$a}), (q:Player {id:$b}) "
                            "CREATE (p)-[:CONFLICT_WITH {kind:$k, severity:$s, "
                            "article_id:$art, occurred:$o}]->(q)",
                            {
                                "a": x, "b": y, "k": c["kind"], "s": c["severity"],
                                "art": a["id"], "o": a["published_at"],
                            },
                        )

        # r4: draftClassmateOf
        by_year: dict[int, list[str]] = defaultdict(list)
        for p in players:
            by_year[p["draft_year"]].append(p["id"])
        for year, members in by_year.items():
            if len(members) < 2:
                continue
            for i, a in enumerate(members):
                for b in members[i + 1 :]:
                    for x, y in ((a, b), (b, a)):
                        self._run(
                            "MATCH (p:Player {id:$a}), (q:Player {id:$b}) "
                            "CREATE (p)-[:DRAFT_CLASSMATE {draft_year:$y}]->(q)",
                            {"a": x, "b": y, "y": year},
                        )

        # r5: divisionRivalOf
        by_div: dict[str, list[str]] = defaultdict(list)
        for t in teams:
            by_div[t["division"]].append(t["id"])
        for div, members in by_div.items():
            for i, a in enumerate(members):
                for b in members[i + 1 :]:
                    for x, y in ((a, b), (b, a)):
                        self._run(
                            "MATCH (p:Team {id:$a}), (q:Team {id:$b}) "
                            "CREATE (p)-[:DIVISION_RIVAL {division:$d}]->(q)",
                            {"a": x, "b": y, "d": div},
                        )

    # -- execution ---------------------------------------------------------

    def _run(self, cypher: str, params: dict | None = None) -> Any:
        return self.conn.execute(cypher, parameters=params or {})

    def query(self, cypher: str, limit: int = 50) -> tuple[list[str], list[list[Any]]]:
        """Run read-only Cypher and return (column names, rows)."""
        guard = cypher.strip().rstrip(";")
        lowered = guard.lower()
        for banned in ("create ", "delete ", "detach ", "set ", "merge ", "drop ", "copy ", "alter "):
            if banned in lowered:
                raise ValueError(f"Only read queries are allowed (found '{banned.strip()}').")
        result = self.conn.execute(guard)
        cols = result.get_column_names()
        rows: list[list[Any]] = []
        while result.has_next() and len(rows) < limit:
            rows.append([_jsonable(v) for v in result.get_next()])
        return cols, rows

    def _count(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for label in ("Player", "Team", "Article", "Trade"):
            _, rows = self.query(f"MATCH (n:{label}) RETURN count(n)", limit=1)
            out[label] = rows[0][0] if rows else 0
        for rel, pattern in (
            ("PLAYS_FOR", "(:Player)-[r:PLAYS_FOR]->(:Team)"),
            ("PLAYED_FOR", "(:Player)-[r:PLAYED_FOR]->(:Team)"),
            ("TEAMMATE", "(:Player)-[r:TEAMMATE]->(:Player)"),
            ("FORMER_TEAMMATE", "(:Player)-[r:FORMER_TEAMMATE]->(:Player)"),
            ("CONFLICT_WITH", "(:Player)-[r:CONFLICT_WITH]->(:Player)"),
            ("DRAFT_CLASSMATE", "(:Player)-[r:DRAFT_CLASSMATE]->(:Player)"),
            ("DIVISION_RIVAL", "(:Team)-[r:DIVISION_RIVAL]->(:Team)"),
            ("MENTIONED_IN", "(:Player)-[r:MENTIONED_IN]->(:Article)"),
            ("INVOLVED_IN", "(:Player)-[r:INVOLVED_IN]->(:Trade)"),
        ):
            _, rows = self.query(f"MATCH {pattern} RETURN count(r)", limit=1)
            out[rel] = rows[0][0] if rows else 0
        return out


def _jsonable(value: Any) -> Any:
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value
