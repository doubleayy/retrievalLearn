import Link from "next/link";

import { CodeBlock } from "@/components/CodeBlock";

const LESSONS = [
  {
    id: "keyword",
    accent: "#f5a524",
    name: "Keyword search",
    language: "SQL · SQLite FTS5",
    idea:
      "Build an inverted index: for every word, keep the list of documents containing it. To search, intersect those lists and rank the survivors by BM25 — a formula that rewards rare terms and penalises long documents.",
    code: `SELECT d.title, bm25(documents_fts, 2.0, 1.0) AS score
FROM documents_fts
JOIN documents AS d ON d.doc_rowid = documents_fts.rowid
WHERE documents_fts MATCH 'draymond OR green AND suspend*'
ORDER BY score
LIMIT 10`,
    good: [
      "Names, codes, identifiers — anything you can spell exactly.",
      "Sub-millisecond latency with no model in the loop.",
      "Perfectly explainable: you can point at the tokens that matched.",
    ],
    bad: [
      "It matches strings, not meaning. Searching 'beef' in this corpus returns a brisket article, a beef Wellington article and a weight-training article before it reaches the one real feud.",
      "A document saying 'bad blood' is invisible to a search for 'feud'.",
      "It cannot express a threshold, a count, or a relationship.",
    ],
  },
  {
    id: "semantic",
    accent: "#22b8cf",
    name: "Semantic search",
    language: "SQL · sqlite-vec",
    idea:
      "Run every document through an embedding model that maps text to a point in 384-dimensional space, arranged so that similar meanings land near each other. At query time, embed the question and return its nearest neighbours by cosine distance.",
    code: `SELECT d.title, vec_distance_cosine(v.embedding, :query_vector) AS distance
FROM doc_vectors AS v
JOIN documents AS d ON d.doc_rowid = v.doc_rowid
WHERE v.embedding MATCH :query_vector
  AND k = 10
ORDER BY distance`,
    good: [
      "Paraphrase and synonymy come free — 'rift' matches a query about feuds.",
      "Survives typos and vocabulary the user could not have guessed.",
      "The person searching needs to know nothing about the schema.",
    ],
    bad: [
      "It always returns k results, ranked, with no signal that the top hit is wrong.",
      "It confuses topic with intent. In this corpus, an article whose entire point is the ABSENCE of conflict ranks second for 'players in disputes'.",
      "Precision on names and numbers is poor — embeddings blur exact tokens.",
      "It cannot represent negation. 'Players with no conflicts' embeds almost identically to 'players with conflicts'.",
    ],
  },
  {
    id: "graph",
    accent: "#a78bfa",
    name: "Graph search",
    language: "Cypher · Kuzu",
    idea:
      "Model the world as nodes and edges — players, teams, articles, trades — then match patterns over them. There is no ranking: a row is returned because it satisfies the pattern, or it is not returned at all.",
    code: `MATCH (a:Player)-[c:CONFLICT_WITH]->(b:Player)-[:FORMER_TEAMMATE]->(a)
WHERE a.position IN ['PF', 'C']
RETURN DISTINCT a.name, b.name AS counterpart, c.kind
LIMIT 25`,
    good: [
      "Answers relational questions text search cannot express at all: 'traded twice', 'former teammates who later fell out'.",
      "Exact and complete. No ranking means no silent truncation of the answer.",
      "Can traverse derived edges. FORMER_TEAMMATE here is computed from overlapping season ranges and appears in no source file.",
    ],
    bad: [
      "Brittle. One wrong label and you get zero rows, not approximately-right rows.",
      "It only sees what was modelled. Somebody mentioned in an article but missing from the graph does not exist.",
      "It has no notion of 'about' — it cannot find documents on a theme.",
      "Somebody, or something, has to write correct Cypher first.",
    ],
  },
  {
    id: "hybrid",
    accent: "#4ade80",
    name: "Hybrid search",
    language: "SQL + Cypher",
    idea:
      "Run the retrievers independently and merge their ranked lists. Reciprocal Rank Fusion discards the raw scores — which are on incomparable scales — and keeps only the positions, so a document appearing in two lists beats one that tops a single list.",
    code: `score(d) = Σ over legs of  weight_leg / (60 + rank_leg(d))

# keyword  #1  → 1.0 / 61 = 0.01639
# semantic #4  → 1.0 / 64 = 0.01562
# graph    #2  → 2.5 / 62 = 0.04032   ← a pattern match is a stronger claim`,
    good: [
      "Covers each mode's blind spot: exact names from BM25, paraphrase from vectors, structure from the graph.",
      "Agreement across legs is a genuine relevance signal.",
      "RRF needs no score calibration and almost no tuning.",
    ],
    bad: [
      "Three times the work and three times the latency.",
      "It still only knows the words you used. 'Big men' is two tokens to BM25, a vague direction to the embedder, and nothing at all to Cypher.",
      "Fusion can bury a correct answer that only one leg found.",
    ],
  },
  {
    id: "hybrid_ontology",
    accent: "#f472b6",
    name: "Hybrid + ontology",
    language: "SQL + Cypher + OWL-lite",
    idea:
      "Before retrieving anything, resolve the words in the question against a model of the domain. 'Big man' is not a string — it is a class with an equivalence axiom. 'Beef' is a class with seven subclasses. 'Former teammate' is a relation derived by a rule. Only then do the retrievers run, on rewritten queries.",
    code: `"big men"          → hoops:BigMan  ≡ PowerForward ⊔ Center
                              → position IN ('PF','C')

"beef"             → hoops:Conflict
                              → kind IN ('Beef','OnCourtAltercation',
                                         'LockerRoomIncident','PublicCallout',
                                         'ContractDispute','RoleDispute',
                                         'ConductSuspension')

"former teammate"  → hoops:formerTeammateOf  (derived)
                              → [:FORMER_TEAMMATE]`,
    good: [
      "Turns vocabulary into structure. No amount of embedding similarity gives you position IN ('PF','C').",
      "Subclass closure means asking about 'beef' also finds trade requests and locker room incidents, because they are modelled as kinds of conflict.",
      "Deterministic and auditable — the expansion is a proof you can read, not a model's opinion.",
      "Recovers the precision the vector leg loses: the brisket article is not a member of any conflict class, so it cannot appear.",
    ],
    bad: [
      "Somebody has to build and maintain the ontology. This one is roughly 200 lines of hand-written JSON.",
      "It only helps where the domain was modelled. Unmodelled phrases fall straight through to plain hybrid.",
      "Over-broad expansion hurts: pulling in all seven conflict subclasses surfaces a conduct suspension when you asked about interpersonal feuds.",
      "The closure has to be recomputed whenever the ontology changes.",
    ],
  },
];

const GLOSSARY = [
  [
    "Inverted index",
    "A map from each word to the list of documents containing it. The data structure behind every keyword search engine since the 1970s.",
  ],
  [
    "BM25",
    "The ranking function on top of that index. Rewards rare terms, penalises long documents, and saturates — the tenth occurrence of a word adds much less than the second.",
  ],
  [
    "Embedding",
    "A fixed-length list of numbers representing a piece of text, produced by a neural network trained so that similar meanings produce nearby vectors. Here: 384 numbers per document.",
  ],
  [
    "Cosine similarity",
    "The angle between two vectors, ignoring their length. 1.0 is identical direction, 0 is unrelated. The standard way to compare embeddings.",
  ],
  [
    "Chunking",
    "Splitting long documents so each embedding covers one coherent idea. Not needed here — every document is short enough to embed whole — but it is where most real systems lose the most quality.",
  ],
  [
    "Property graph",
    "Nodes and edges that both carry key-value properties. Cypher is the query language; Neo4j and Kuzu are two implementations.",
  ],
  [
    "Derived edge",
    "A relationship computed rather than stored. FORMER_TEAMMATE is derived from overlapping stints; it is the reason the graph can answer questions the source files cannot.",
  ],
  [
    "RRF",
    "Reciprocal Rank Fusion. Merges ranked lists using positions rather than scores, so you never have to make BM25 and cosine similarity comparable.",
  ],
  [
    "Ontology",
    "A formal model of a domain: classes, how they nest, the relations between them, and rules for inferring new facts. The difference between a synonym list and an ontology is that an ontology can reason.",
  ],
  [
    "Subclass closure",
    "Everything below a class in the hierarchy. Asking for Conflict must also match its seven subclasses, or the answer is silently incomplete.",
  ],
];

const CHOICE = [
  ["You know the exact word or name", "Keyword", "#f5a524"],
  ["You know the idea but not the wording", "Semantic", "#22b8cf"],
  ["The answer is a relationship, a count, or a path", "Graph", "#a78bfa"],
  ["You are not sure which of the above applies", "Hybrid", "#4ade80"],
  ["Your users speak in domain jargon your data does not use", "Hybrid + ontology", "#f472b6"],
];

export default function LearnPage() {
  return (
    <main className="mx-auto max-w-[1400px] px-4 pb-16 pt-8 sm:px-6">
      <section className="mb-10 max-w-3xl">
        <h1 className="text-3xl font-semibold tracking-tight text-ink-100 sm:text-4xl">
          Five ways to find something
        </h1>
        <p className="mt-3 text-[15px] leading-relaxed text-ink-300">
          Every retrieval system is a bet about what makes two things related:
          shared words, nearby meaning, or a modelled connection. The bet you make
          decides which questions you can answer and which ones fail silently.
        </p>
        <p className="mt-3 text-[15px] leading-relaxed text-ink-300">
          Read this, then go{" "}
          <Link href="/" className="text-arena-hybrid underline underline-offset-2">
            break each one in the arena
          </Link>
          .
        </p>
      </section>

      <section className="mb-12 rounded-xl border border-ink-800 bg-ink-900/40 p-5">
        <h2 className="text-[15px] font-semibold text-ink-100">Which one do I want?</h2>
        <ul className="mt-3 space-y-1.5">
          {CHOICE.map(([when, mode, colour]) => (
            <li key={when} className="flex flex-wrap items-baseline gap-2 text-[13px]">
              <span className="text-ink-300">{when}</span>
              <span className="flex-1 border-b border-dotted border-ink-700" />
              <span className="font-mono text-[12px]" style={{ color: colour }}>
                {mode}
              </span>
            </li>
          ))}
        </ul>
        <p className="mt-3.5 text-[12.5px] leading-relaxed text-ink-400">
          In practice most production systems land on hybrid, then spend the next
          year discovering that their users&apos; vocabulary does not match their
          schema — which is the problem the last row solves.
        </p>
      </section>

      <div className="space-y-8">
        {LESSONS.map((l, i) => (
          <article
            key={l.id}
            className="overflow-hidden rounded-2xl border border-ink-800 bg-ink-900/30"
          >
            <div
              className="flex flex-wrap items-baseline gap-3 border-b border-ink-800 px-5 py-3.5"
              style={{ background: `linear-gradient(90deg, ${l.accent}12, transparent 70%)` }}
            >
              <span
                className="font-mono text-[11px] tabular-nums"
                style={{ color: l.accent }}
              >
                {String(i + 1).padStart(2, "0")}
              </span>
              <h2 className="text-[18px] font-semibold tracking-tight text-ink-100">
                {l.name}
              </h2>
              <span className="ml-auto font-mono text-[10.5px] uppercase tracking-widest text-ink-500">
                {l.language}
              </span>
            </div>

            <div className="grid gap-5 p-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
              <div>
                <p className="text-[13.5px] leading-relaxed text-ink-200">{l.idea}</p>
                <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-1">
                  <div>
                    <div className="mb-1.5 font-mono text-[10px] uppercase tracking-widest text-emerald-400">
                      where it wins
                    </div>
                    <ul className="space-y-1">
                      {l.good.map((g) => (
                        <li
                          key={g}
                          className="flex gap-1.5 text-[12.5px] leading-relaxed text-ink-300"
                        >
                          <span className="text-emerald-500">+</span>
                          <span>{g}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <div className="mb-1.5 font-mono text-[10px] uppercase tracking-widest text-rose-400">
                      where it breaks
                    </div>
                    <ul className="space-y-1">
                      {l.bad.map((b) => (
                        <li
                          key={b}
                          className="flex gap-1.5 text-[12.5px] leading-relaxed text-ink-300"
                        >
                          <span className="text-rose-500">−</span>
                          <span>{b}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
              <div>
                <CodeBlock
                  code={l.code}
                  language={l.id === "graph" ? "cypher" : l.id.startsWith("hybrid") ? "text" : "sql"}
                  accent={l.accent}
                />
              </div>
            </div>
          </article>
        ))}
      </div>

      <section className="mt-12">
        <h2 className="text-[20px] font-semibold tracking-tight text-ink-100">
          Glossary
        </h2>
        <dl className="mt-4 grid gap-3 sm:grid-cols-2">
          {GLOSSARY.map(([term, def]) => (
            <div
              key={term}
              className="rounded-xl border border-ink-800 bg-ink-900/40 p-3.5"
            >
              <dt className="text-[13px] font-semibold text-ink-100">{term}</dt>
              <dd className="mt-1 text-[12.5px] leading-relaxed text-ink-300">{def}</dd>
            </div>
          ))}
        </dl>
      </section>
    </main>
  );
}
