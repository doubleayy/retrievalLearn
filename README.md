# Retrieval Arena

**See how machines find things.**

A teaching sandbox that runs the same question through five different retrieval
strategies over one corpus, and shows you the actual SQL or Cypher that each one
executed — plus where it quietly falls apart.

| Mode | Engine | Query language |
|---|---|---|
| Keyword search | SQLite FTS5, BM25 | SQL |
| Semantic search | sqlite-vec, cosine KNN over `bge-small-en-v1.5` | SQL |
| Graph search | Kuzu embedded property graph | Cypher |
| Hybrid | all three, weighted Reciprocal Rank Fusion | SQL + Cypher |
| Hybrid + ontology | the above, with domain-model query expansion first | SQL + Cypher + OWL-lite |

Every query shown in the UI is the query that ran. Nothing is illustrative.

---

## The corpus

A hand-authored basketball dataset chosen because it has all three data shapes
at once — structured rows, unstructured prose, and a genuine graph.

- **38 players** with positions, per-game production, salary and draft provenance
- **25 teams**, 12 of them carrying a current roster
- **69 roster stints** spanning 2008–2025 — the table that makes "former teammate" computable
- **21 trades** with 22 player legs and 29 draft picks, protections included
- **44 news articles**, of which 16 describe a conflict and **6 are deliberate retrieval traps**
- **20 derived conflict edges**, materialised from the articles by an ontology rule
- **103 searchable documents** (articles + player bios + trade summaries), indexed identically for keyword and vector search so the comparison is fair
- **A 37-class ontology** with 10 equivalence axioms and 5 inference rules

### The traps are the point

Three articles contain the word *beef* and are about brisket, beef Wellington and
weight training. Several articles describe real disputes without using a single
word of conflict vocabulary. One article's entire subject is the *absence* of
conflict, and it embeds very close to articles about conflict.

The result: searching `beef` in keyword mode returns three food and fitness
articles before it reaches the one real feud explainer. Searching the same idea
semantically returns the "absence of conflict" article at rank two. Only the
ontology mode gets it right, and the app shows you exactly why.

### Data provenance

Player statistics are approximate public-record values for roughly the 2023-24
season. The articles are **original neutral summaries of publicly reported
events, written for this demo** — they are not reproductions of real published
articles and contain no invented quotes. This is stated in the app's footer and
in the data catalog.

---

## The showcase query

```
which big men have beef with a former teammate?
```

No document in the corpus contains the phrase "big man" anywhere near a conflict.
To answer this you need three separate translations:

- `big men` → a class with an equivalence axiom → `position IN ('PF','C')`
- `beef` → a class with seven subclasses → `kind IN (...7 conflict kinds...)`
- `former teammate` → a **derived** edge computed from overlapping season ranges

Keyword mode returns brisket. Semantic mode returns a documentary about the
1980s. Ontology mode assembles this, deterministically, with no model call:

```cypher
MATCH (a:Player)-[r0:CONFLICT_WITH]->(b:Player)-[r1:FORMER_TEAMMATE]->(a)
WHERE a.position IN ['PF', 'C']
  AND r0.kind IN ['Beef', 'ConductSuspension', 'ContractDispute',
                  'LockerRoomIncident', 'OnCourtAltercation',
                  'PublicCallout', 'RoleDispute']
RETURN DISTINCT a.id AS id, a.name AS name, a.position AS position,
       b.name AS counterpart, r0.kind AS relation_detail
LIMIT 25
```

…and returns Draymond Green, Karl-Anthony Towns and Joel Embiid.

---

## Architecture

```
retrievalLearn/
├── apps/
│   ├── api/                      FastAPI  →  Railway (Docker)
│   │   ├── app/
│   │   │   ├── main.py           endpoints, CORS, rate limiting
│   │   │   ├── planner.py        Claude: natural language → SQL + Cypher
│   │   │   ├── ontology.py       OWL-lite reasoner (subclass closure, Turtle)
│   │   │   ├── expansion.py      deterministic ontology query rewriting
│   │   │   ├── index.py          builds and holds every store
│   │   │   ├── precompute.py     bakes document vectors at image build time
│   │   │   ├── catalog.py        data catalog + curated example queries
│   │   │   ├── stores/           relational.py · vectors.py · graph.py
│   │   │   └── retrievers/       keyword · semantic · graphsearch · hybrid
│   │   └── data/                 JSON seed files + embeddings.npz
│   └── web/                      Next.js 15 App Router  →  Vercel
│       ├── app/                  / (arena) · /catalog · /learn
│       ├── components/           ModePicker · ResultList · UnderTheHood · CodeBlock
│       └── lib/api.ts            typed client
```

**No database to provision.** SQLite, sqlite-vec and Kuzu are all embedded and
rebuilt from JSON on every boot (~5 seconds). One Railway service, no add-ons.

### How a query flows

1. **Plan** — one Claude call turns your question into an FTS5 match expression,
   a rewritten string to embed, a Cypher statement, and a SQL filter. All four
   at once, so the UI can show what the *other* modes would have done. The system
   prompt is static and cached; plans are cached per-query in-process.
2. **Expand** (ontology mode only) — the raw question is matched against the
   ontology in-process. No model call, so the expansion trace is a proof you can
   read rather than an opinion you have to trust.
3. **Retrieve** — the selected mode executes. Cypher failures get one repair pass
   with the parser error fed back to Claude; both attempts are shown.
4. **Fuse** (hybrid modes) — weighted RRF over the legs, with the graph leg
   weighted 2.5× because a pattern match is a stronger claim than a good rank.

---

## Running locally

### Backend

```bash
cd apps/api
python -m venv .venv
.venv/Scripts/activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt

python -m app.precompute        # embeds the corpus once (~25s, cached after)

export ANTHROPIC_API_KEY=sk-ant-...
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000/api/health — it reports the build, the vector engine
in use, and whether the planner has a key.

### Frontend

```bash
cd apps/web
npm install
npm run dev        # reads NEXT_PUBLIC_API_URL from .env.local
```

http://localhost:3000

---

## Deploying

### Backend → Railway

1. Push this repo to GitHub.
2. Railway → **New Project → Deploy from GitHub repo**.
3. **Settings → Root Directory**: `apps/api`. Railway picks up `railway.toml` and
   builds the Dockerfile.
4. **Variables**: set `ANTHROPIC_API_KEY`. Everything else has a working default.
5. **Settings → Networking → Generate Domain**. Copy the URL.
6. Set `CORS_ORIGINS` to your Vercel URL once you have it (Vercel preview
   deployments are already matched by `CORS_ORIGIN_REGEX`).

The image bakes in both the embedding model and the document vectors, so cold
starts are a few seconds rather than half a minute. The healthcheck allows a
90-second start period.

### Frontend → Vercel

1. Vercel → **Add New → Project**, import the same repo.
2. **Root Directory**: `apps/web`.
3. **Environment Variables**: `NEXT_PUBLIC_API_URL` = your Railway URL, no
   trailing slash.
4. Deploy.

### Environment variables

| Variable | Where | Default | Notes |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Railway | — | **Required.** Without it `/api/search` returns a clear 503. |
| `PLANNER_MODEL` | Railway | `claude-opus-5` | See **Choosing a planner model** below. |
| `PLANNER_EFFORT` | Railway | `low` | Planning is a translation task; low effort is enough. |
| `CORS_ORIGINS` | Railway | localhost:3000 | Comma-separated exact origins. |
| `CORS_ORIGIN_REGEX` | Railway | `https://.*\.vercel\.app` | Matches preview deployments. |
| `RATE_LIMIT_PER_MIN` | Railway | `20` | Per IP, in-memory. |
| `KUZU_BUFFER_POOL_MB` | Railway | `96` | **Must stay small.** See below. |
| `EMBED_THREADS` | Railway | `2` | onnxruntime thread pool. |
| `NEXT_PUBLIC_API_URL` | Vercel | localhost:8000 | Railway URL, no trailing slash. |

### Container memory

Two of the libraries here size themselves against the *host* machine rather than
the container's cgroup limit, which makes them OOM-kill the process on a small
instance:

- **Kuzu** defaults `buffer_pool_size` to ~80% of system memory. On a Railway
  host that is tens of gigabytes reserved inside a container capped at a few
  hundred MB — the process dies about a second into startup with a bare `Killed`
  and no traceback. `KUZU_BUFFER_POOL_MB=96` fixes it; the graph is 38 nodes and
  ~500 edges, so this is not a compromise.
- **onnxruntime** sizes its thread pool to the host CPU count. Capped via
  `EMBED_THREADS` and `OMP_NUM_THREADS=1`, which matters on the first semantic
  query rather than at boot.

Steady-state RSS is roughly 400 MB once the embedding model has loaded, so give
the service **at least 512 MB**, ideally 1 GB.

---

## Choosing a planner model

`PLANNER_MODEL` is a pure environment-variable change — no redeploy of code
needed, just restart the service.

| Model | Input / output per MTok | Notes |
|---|---|---|
| `claude-opus-5` (default) | $5 / $25 | Best Cypher accuracy. |
| `claude-sonnet-5` | $2 / $10 | 2.5x cheaper. The sensible default for a public demo. |
| `claude-haiku-4-5` | $1 / $5 | 5x cheaper. Expect more Cypher repair passes. |

`output_config.effort` is **rejected with a 400 on Haiku 4.5** and other pre-4.6
models, so `planner.py` gates it via `supports_effort()`. Without that gate,
switching to Haiku would fail every query. Setting `PLANNER_EFFORT=""` disables
effort for any model.

---

## Cost

Only the planner costs money — one Claude call per unique question, cached
in-process afterwards. The system prompt is ~1,550 tokens and marked for caching;
output is ~400 tokens of JSON. Embeddings run locally and are free. If you expose
this publicly, `PLANNER_MODEL=claude-haiku-4-5` plus the built-in rate limit is a
sensible combination.

---

## Editing the corpus

All seed data is JSON in `apps/api/data/`. Add an article to `news.json`, give it
a `conflict` block if it describes one, then:

```bash
python -m app.precompute     # detects the change via fingerprint and re-embeds
```

The graph, the FTS index and the derived edges all rebuild automatically on the
next boot. Extending `ontology.json` needs no code change at all — new classes,
synonyms and equivalence axioms are picked up by the reasoner as-is.

---

## What is verified, and what is not

Everything in this repository has been run except one thing: the Claude planner
call was never executed against the live API, because no Anthropic credentials
were available in the build environment. The request shape was written against
the current Anthropic Python SDK (1.4.0) and the parameter names were checked
against the installed signature, but the first real `POST /api/search` is
unproven. Set `ANTHROPIC_API_KEY` and try the showcase query first.

Verified: the index build, all five retrieval modes end to end through the
endpoint, response serialisation, FTS5 and Cypher execution, the ontology
reasoner and expansion, the precompute cache, every read-only endpoint over
HTTP, and the production build of the web app.
