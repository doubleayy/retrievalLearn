"""SQLite: the structured store and the keyword index.

Keyword retrieval here is real BM25 out of SQLite's FTS5 module, not a
similarity score dressed up as one. The SQL shown in the UI is the SQL that
ran.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

SCHEMA = """
PRAGMA journal_mode = WAL;

CREATE TABLE teams (
    id                 TEXT PRIMARY KEY,
    name               TEXT NOT NULL,
    city               TEXT NOT NULL,
    conference         TEXT NOT NULL,
    division           TEXT NOT NULL,
    arena              TEXT NOT NULL,
    has_current_roster INTEGER NOT NULL
);

CREATE TABLE players (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    team_id    TEXT NOT NULL REFERENCES teams(id),
    position   TEXT NOT NULL,
    height_in  INTEGER NOT NULL,
    weight_lb  INTEGER NOT NULL,
    age        INTEGER NOT NULL,
    ppg        REAL NOT NULL,
    rpg        REAL NOT NULL,
    apg        REAL NOT NULL,
    spg        REAL NOT NULL,
    bpg        REAL NOT NULL,
    fg3_pct    REAL NOT NULL,
    salary_usd INTEGER NOT NULL,
    draft_year INTEGER NOT NULL,
    draft_pick INTEGER,
    college    TEXT NOT NULL,
    country    TEXT NOT NULL,
    bio        TEXT NOT NULL
);

CREATE TABLE stints (
    player_id   TEXT NOT NULL REFERENCES players(id),
    team_id     TEXT NOT NULL REFERENCES teams(id),
    from_season INTEGER NOT NULL,
    to_season   INTEGER NOT NULL
);

CREATE TABLE trades (
    id      TEXT PRIMARY KEY,
    date    TEXT NOT NULL,
    window  TEXT NOT NULL,
    type    TEXT NOT NULL,
    summary TEXT NOT NULL
);

CREATE TABLE trade_legs (
    trade_id  TEXT NOT NULL REFERENCES trades(id),
    player_id TEXT NOT NULL REFERENCES players(id),
    from_team TEXT NOT NULL REFERENCES teams(id),
    to_team   TEXT NOT NULL REFERENCES teams(id)
);

CREATE TABLE trade_picks (
    trade_id   TEXT NOT NULL REFERENCES trades(id),
    from_team  TEXT NOT NULL REFERENCES teams(id),
    to_team    TEXT NOT NULL REFERENCES teams(id),
    year       INTEGER NOT NULL,
    round      INTEGER NOT NULL,
    protection TEXT NOT NULL
);

CREATE TABLE articles (
    id             TEXT PRIMARY KEY,
    title          TEXT NOT NULL,
    body           TEXT NOT NULL,
    published_at   TEXT NOT NULL,
    source_type    TEXT NOT NULL,
    tags           TEXT NOT NULL,
    teams          TEXT NOT NULL,
    entities       TEXT NOT NULL,
    conflict_kind  TEXT,
    retrieval_note TEXT NOT NULL
);

-- Derived: one row per ordered pair of players named in the same conflict.
CREATE TABLE conflict_edges (
    article_id TEXT NOT NULL REFERENCES articles(id),
    player_a   TEXT NOT NULL REFERENCES players(id),
    player_b   TEXT NOT NULL REFERENCES players(id),
    kind       TEXT NOT NULL,
    severity   TEXT NOT NULL,
    occurred   TEXT NOT NULL
);

-- The unified text corpus. Player bios, trade summaries and articles all end
-- up here so that keyword and vector search see exactly the same documents.
CREATE TABLE documents (
    doc_rowid INTEGER PRIMARY KEY,
    id        TEXT UNIQUE NOT NULL,
    kind      TEXT NOT NULL,
    ref_id    TEXT NOT NULL,
    title     TEXT NOT NULL,
    body      TEXT NOT NULL,
    meta      TEXT NOT NULL
);

CREATE VIRTUAL TABLE documents_fts USING fts5(
    title,
    body,
    content='documents',
    content_rowid='doc_rowid',
    tokenize='porter unicode61'
);

CREATE INDEX idx_players_position ON players(position);
CREATE INDEX idx_stints_player ON stints(player_id);
CREATE INDEX idx_stints_team ON stints(team_id);
CREATE INDEX idx_conflict_a ON conflict_edges(player_a);
"""


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def build(path: Path, data_dir: Path) -> sqlite3.Connection:
    """Create the database from the JSON seed files. Idempotent by deletion."""
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(path) + suffix)
        if not p.exists():
            continue
        try:
            p.unlink()
        except PermissionError as exc:  # Windows keeps a lock while a process holds it
            raise RuntimeError(
                f"Cannot rebuild {p}: another process still has it open. "
                f"Stop any running API process (or set BUILD_DIR to a fresh path) "
                f"and start again."
            ) from exc
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = connect(path)
    conn.executescript(SCHEMA)

    def load(name: str) -> Any:
        with open(data_dir / f"{name}.json", encoding="utf-8") as fh:
            return json.load(fh)

    teams = load("teams")
    players = load("players")
    stints = load("stints")
    trades = load("trades")
    news = load("news")

    conn.executemany(
        "INSERT INTO teams VALUES (:id,:name,:city,:conference,:division,:arena,:has_current_roster)",
        [{**t, "has_current_roster": int(t["has_current_roster"])} for t in teams],
    )
    conn.executemany(
        """INSERT INTO players VALUES (:id,:name,:team_id,:position,:height_in,:weight_lb,:age,
           :ppg,:rpg,:apg,:spg,:bpg,:fg3_pct,:salary_usd,:draft_year,:draft_pick,:college,:country,:bio)""",
        players,
    )
    conn.executemany(
        "INSERT INTO stints VALUES (:player_id,:team_id,:from_season,:to_season)", stints
    )
    conn.executemany(
        "INSERT INTO trades VALUES (:id,:date,:window,:type,:summary)",
        [{k: t[k] for k in ("id", "date", "window", "type", "summary")} for t in trades],
    )
    conn.executemany(
        "INSERT INTO trade_legs VALUES (?,?,?,?)",
        [
            (t["id"], leg["player_id"], leg["from_team"], leg["to_team"])
            for t in trades
            for leg in t["legs"]
        ],
    )
    conn.executemany(
        "INSERT INTO trade_picks VALUES (?,?,?,?,?,?)",
        [
            (t["id"], p["from_team"], p["to_team"], p["year"], p["round"], p["protection"])
            for t in trades
            for p in t["picks"]
        ],
    )

    conn.executemany(
        """INSERT INTO articles VALUES (:id,:title,:body,:published_at,:source_type,
           :tags,:teams,:entities,:conflict_kind,:retrieval_note)""",
        [
            {
                "id": a["id"],
                "title": a["title"],
                "body": a["body"],
                "published_at": a["published_at"],
                "source_type": a["source_type"],
                "tags": json.dumps(a["tags"]),
                "teams": json.dumps(a["teams"]),
                "entities": json.dumps(a["entities"]),
                "conflict_kind": (a["conflict"] or {}).get("kind"),
                "retrieval_note": a.get("retrieval_note", ""),
            }
            for a in news
        ],
    )

    # Rule r3: two players named in the same conflict event are in conflict.
    edges = []
    for a in news:
        c = a.get("conflict")
        if not c:
            continue
        parts = c["participants"]
        for i, pa in enumerate(parts):
            for pb in parts[i + 1 :]:
                edges.append((a["id"], pa, pb, c["kind"], c["severity"], a["published_at"]))
                edges.append((a["id"], pb, pa, c["kind"], c["severity"], a["published_at"]))
    conn.executemany("INSERT INTO conflict_edges VALUES (?,?,?,?,?,?)", edges)

    # --- unified document corpus -----------------------------------------
    docs: list[tuple[str, str, str, str, str, str]] = []
    for a in news:
        docs.append(
            (
                f"article:{a['id']}",
                "article",
                a["id"],
                a["title"],
                a["body"],
                json.dumps(
                    {
                        "published_at": a["published_at"],
                        "source_type": a["source_type"],
                        "tags": a["tags"],
                        "entities": a["entities"],
                        "conflict_kind": (a["conflict"] or {}).get("kind"),
                        "retrieval_note": a.get("retrieval_note", ""),
                    }
                ),
            )
        )
    for p in players:
        docs.append(
            (
                f"player:{p['id']}",
                "player",
                p["id"],
                f"{p['name']} scouting profile",
                p["bio"],
                json.dumps(
                    {
                        "position": p["position"],
                        "team_id": p["team_id"],
                        "age": p["age"],
                        "ppg": p["ppg"],
                        "fg3_pct": p["fg3_pct"],
                    }
                ),
            )
        )
    for t in trades:
        docs.append(
            (
                f"trade:{t['id']}",
                "trade",
                t["id"],
                f"{t['window']}: {t['summary'][:60]}",
                t["summary"],
                json.dumps({"date": t["date"], "window": t["window"], "type": t["type"]}),
            )
        )

    conn.executemany(
        "INSERT INTO documents (id, kind, ref_id, title, body, meta) VALUES (?,?,?,?,?,?)",
        docs,
    )
    conn.execute(
        "INSERT INTO documents_fts (rowid, title, body) "
        "SELECT doc_rowid, title, body FROM documents"
    )
    conn.commit()
    return conn


def table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    tables = [
        "teams",
        "players",
        "stints",
        "trades",
        "trade_legs",
        "trade_picks",
        "articles",
        "conflict_edges",
        "documents",
    ]
    return {
        t: conn.execute(f"SELECT count(*) AS n FROM {t}").fetchone()["n"] for t in tables
    }


def all_documents(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT doc_rowid, id, kind, ref_id, title, body, meta FROM documents ORDER BY doc_rowid"
    ).fetchall()
