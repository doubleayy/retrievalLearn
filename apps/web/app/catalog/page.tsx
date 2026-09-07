"use client";

import { useEffect, useState } from "react";

import { CodeBlock } from "@/components/CodeBlock";
import {
  getCatalog,
  getOntology,
  MODE_ACCENT,
  type CatalogResponse,
  type ModeId,
  type OntologyResponse,
} from "@/lib/api";

const SHAPE_STYLE: Record<string, string> = {
  structured: "bg-emerald-500/10 text-emerald-300 ring-emerald-500/25",
  "structured / temporal": "bg-teal-500/10 text-teal-300 ring-teal-500/25",
  "unstructured text": "bg-sky-500/10 text-sky-300 ring-sky-500/25",
  "graph / event": "bg-violet-500/10 text-violet-300 ring-violet-500/25",
  "derived graph": "bg-fuchsia-500/10 text-fuchsia-300 ring-fuchsia-500/25",
  "text index": "bg-amber-500/10 text-amber-300 ring-amber-500/25",
  "OWL-lite": "bg-rose-500/10 text-rose-300 ring-rose-500/25",
};

function SampleTable({ rows }: { rows: Record<string, unknown>[] }) {
  if (!rows.length) return null;
  const cols = Object.keys(rows[0]);
  return (
    <div className="scroll-slim overflow-x-auto rounded-lg border border-ink-800">
      <table className="w-full font-mono text-[11px]">
        <thead>
          <tr className="bg-ink-950/60 text-ink-500">
            {cols.map((c) => (
              <th key={c} className="whitespace-nowrap px-2 py-1 text-left font-normal">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-ink-800 text-ink-300">
              {cols.map((c) => {
                const v = r[c];
                const s = v === null || v === undefined ? "null" : String(v);
                return (
                  <td key={c} className="px-2 py-1 align-top" title={s}>
                    <span className="block max-w-[26ch] truncate">
                      {v === null || v === undefined ? (
                        <span className="text-ink-600">null</span>
                      ) : (
                        s
                      )}
                    </span>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function CatalogPage() {
  const [tab, setTab] = useState<"data" | "ontology" | "graph">("data");
  const [catalog, setCatalog] = useState<CatalogResponse | null>(null);
  const [onto, setOnto] = useState<OntologyResponse | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getCatalog().then(setCatalog).catch((e) => setError(String(e)));
    getOntology().then(setOnto).catch(() => undefined);
  }, []);

  return (
    <main className="mx-auto max-w-[1400px] px-4 pb-16 pt-8 sm:px-6">
      <section className="mb-6 max-w-3xl">
        <h1 className="text-3xl font-semibold tracking-tight text-ink-100">
          Data catalog
        </h1>
        <p className="mt-3 text-[15px] leading-relaxed text-ink-300">
          Retrieval results are meaningless if you do not know what is in the box.
          Here is everything the arena can see, which modes can see it, and how much
          of it is derived rather than stored.
        </p>
      </section>

      <div className="mb-6 flex gap-1 border-b border-ink-800">
        {(
          [
            ["data", "Datasets"],
            ["ontology", "Ontology"],
            ["graph", "Graph & build"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={`-mb-px border-b-2 px-3 py-2 text-[13px] transition ${
              tab === id
                ? "border-ink-200 text-ink-100"
                : "border-transparent text-ink-400 hover:text-ink-200"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {error ? (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/5 p-4 text-[13px] text-rose-200">
          Could not reach the API. {error}
        </div>
      ) : null}

      {tab === "data" && catalog ? (
        <>
          <p className="mb-5 max-w-4xl rounded-xl border border-ink-800 bg-ink-900/30 p-3 text-[12px] leading-relaxed text-ink-400">
            {catalog.disclaimer}
          </p>
          <div className="grid gap-4 lg:grid-cols-2">
            {catalog.datasets.map((d) => (
              <article
                key={d.id}
                className="rounded-xl border border-ink-800 bg-ink-900/40 p-4"
              >
                <div className="flex flex-wrap items-baseline gap-2">
                  <h2 className="text-[15px] font-semibold text-ink-100">{d.name}</h2>
                  <span
                    className={`rounded px-1.5 py-px font-mono text-[9.5px] uppercase tracking-wider ring-1 ring-inset ${
                      SHAPE_STYLE[d.shape] ?? "bg-ink-800 text-ink-300 ring-ink-700"
                    }`}
                  >
                    {d.shape}
                  </span>
                  <span className="ml-auto font-mono text-[12px] tabular-nums text-ink-200">
                    {d.row_count.toLocaleString()}
                    <span className="ml-1 text-[10px] text-ink-500">rows</span>
                  </span>
                </div>

                <p className="mt-1 font-mono text-[10.5px] text-ink-500">{d.table}</p>
                <p className="mt-2 text-[12.5px] leading-relaxed text-ink-300">
                  {d.description}
                </p>

                <div className="mt-3">
                  <div className="mb-1 font-mono text-[10px] uppercase tracking-widest text-ink-500">
                    schema · {d.grain}
                  </div>
                  <dl className="space-y-0.5">
                    {d.columns.map((c, i) => (
                      <div key={i} className="flex gap-2 font-mono text-[11px]">
                        <dt className="w-[13rem] shrink-0 truncate text-ink-200">{c[0]}</dt>
                        <dd className="w-16 shrink-0 text-ink-500">{c[1]}</dd>
                        <dd className="min-w-0 flex-1 truncate text-ink-400" title={c[2]}>
                          {c[2]}
                        </dd>
                      </div>
                    ))}
                  </dl>
                </div>

                {d.sample.length ? (
                  <details className="mt-3">
                    <summary className="cursor-pointer font-mono text-[10.5px] uppercase tracking-widest text-ink-500 hover:text-ink-300">
                      sample rows
                    </summary>
                    <div className="mt-2">
                      <SampleTable rows={d.sample} />
                    </div>
                  </details>
                ) : null}

                <div className="mt-3 flex flex-wrap items-center gap-1.5">
                  <span className="text-[11px] text-ink-500">visible to:</span>
                  {(d.visible_to as ModeId[]).map((m) => (
                    <span
                      key={m}
                      className="rounded border px-1.5 py-px font-mono text-[10px]"
                      style={{
                        borderColor: `${MODE_ACCENT[m]}44`,
                        color: MODE_ACCENT[m],
                      }}
                    >
                      {m}
                    </span>
                  ))}
                </div>

                <p className="mt-2.5 border-l-2 border-ink-700 pl-2.5 text-[11.5px] italic leading-relaxed text-ink-400">
                  {d.note}
                </p>
              </article>
            ))}
          </div>
        </>
      ) : null}

      {tab === "ontology" && onto ? (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,26rem)]">
          <div className="space-y-5">
            <section className="rounded-xl border border-ink-800 bg-ink-900/40 p-4">
              <h2 className="text-[15px] font-semibold text-ink-100">
                Defined classes
              </h2>
              <p className="mt-1 text-[12.5px] leading-relaxed text-ink-400">
                These are the ones that matter. Each has an equivalence axiom that
                compiles down to a predicate, which is how a phrase like &quot;big
                man&quot; becomes something a database can execute.
              </p>
              <div className="mt-3 space-y-2">
                {onto.classes
                  .filter((c) => c.defined)
                  .map((c) => (
                    <div
                      key={c.id}
                      className="rounded-lg border border-ink-800 bg-ink-950/50 p-2.5"
                    >
                      <div className="flex flex-wrap items-baseline gap-2">
                        <span className="font-mono text-[12.5px] text-arena-ontology">
                          hoops:{c.id}
                        </span>
                        <span className="font-mono text-[11.5px] text-ink-400">
                          ≡ {c.equivalent_to}
                        </span>
                        <span className="ml-auto font-mono text-[11px] text-ink-500">
                          {onto.defined_class_members[c.id]?.length ?? 0} members
                        </span>
                      </div>
                      <div className="mt-1.5 font-mono text-[11px] text-emerald-300">
                        {c.sql_predicate}
                      </div>
                      <p className="mt-1.5 text-[11px] text-ink-500">
                        also written as:{" "}
                        {(c.synonyms ?? []).slice(0, 6).join(", ")}
                      </p>
                      {onto.defined_class_members[c.id]?.length ? (
                        <p className="mt-1.5 text-[11.5px] text-ink-300">
                          {onto.defined_class_members[c.id].slice(0, 8).join(" · ")}
                          {onto.defined_class_members[c.id].length > 8 ? " …" : ""}
                        </p>
                      ) : null}
                    </div>
                  ))}
              </div>
            </section>

            <section className="rounded-xl border border-ink-800 bg-ink-900/40 p-4">
              <h2 className="text-[15px] font-semibold text-ink-100">
                Inference rules
              </h2>
              <p className="mt-1 text-[12.5px] leading-relaxed text-ink-400">
                Edges produced by these rules exist in no source file. They are
                computed when the graph is built.
              </p>
              <div className="mt-3 space-y-2">
                {onto.rules.map((r) => (
                  <div
                    key={r.id}
                    className="rounded-lg border border-ink-800 bg-ink-950/50 p-2.5"
                  >
                    <div className="font-mono text-[11.5px] leading-relaxed">
                      <span className="text-arena-graph">{r.head}</span>
                      <span className="text-ink-500"> ← </span>
                      <span className="text-ink-200">{r.body}</span>
                    </div>
                    <p className="mt-1.5 text-[11.5px] leading-relaxed text-ink-400">
                      {r.description}
                    </p>
                  </div>
                ))}
              </div>
            </section>
          </div>

          <div className="space-y-5">
            <section className="rounded-xl border border-ink-800 bg-ink-900/40 p-4">
              <h2 className="text-[15px] font-semibold text-ink-100">
                Conflict hierarchy
              </h2>
              <p className="mt-1 text-[12.5px] leading-relaxed text-ink-400">
                Asking about &quot;beef&quot; expands to all of these, which is both
                the feature and the failure mode.
              </p>
              <div className="mt-2.5 flex flex-wrap gap-1.5">
                {onto.conflict_kinds.map((k) => (
                  <span
                    key={k}
                    className="rounded border border-rose-500/25 bg-rose-500/5 px-1.5 py-0.5 font-mono text-[11px] text-rose-300"
                  >
                    {k}
                  </span>
                ))}
              </div>
            </section>

            <section className="rounded-xl border border-ink-800 bg-ink-900/40 p-4">
              <h2 className="mb-2.5 text-[15px] font-semibold text-ink-100">
                Full ontology (Turtle)
              </h2>
              <div className="max-h-[36rem] overflow-y-auto scroll-slim">
                <CodeBlock code={onto.turtle} language="text" accent="#f472b6" dense />
              </div>
            </section>
          </div>
        </div>
      ) : null}

      {tab === "graph" && catalog ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <section className="rounded-xl border border-ink-800 bg-ink-900/40 p-4 sm:col-span-2">
            <h2 className="text-[15px] font-semibold text-ink-100">Graph contents</h2>
            <p className="mt-1 text-[12.5px] leading-relaxed text-ink-400">
              Node and relationship counts in the Kuzu database. The four marked
              &quot;derived&quot; were computed at build time from the tables on the
              left, not loaded from a file.
            </p>
            <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
              {Object.entries(catalog.graph).map(([k, v]) => {
                const derived = [
                  "TEAMMATE",
                  "FORMER_TEAMMATE",
                  "CONFLICT_WITH",
                  "DRAFT_CLASSMATE",
                  "DIVISION_RIVAL",
                ].includes(k);
                return (
                  <div
                    key={k}
                    className={`rounded-lg border px-2.5 py-2 ${
                      derived
                        ? "border-violet-500/25 bg-violet-500/5"
                        : "border-ink-800 bg-ink-950/50"
                    }`}
                  >
                    <div className="font-mono text-[10.5px] text-ink-400">{k}</div>
                    <div className="mt-0.5 font-mono text-[15px] tabular-nums text-ink-100">
                      {v}
                    </div>
                    {derived ? (
                      <div className="font-mono text-[9px] uppercase tracking-wider text-violet-400">
                        derived
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </section>

          <section className="rounded-xl border border-ink-800 bg-ink-900/40 p-4">
            <h2 className="text-[15px] font-semibold text-ink-100">Build</h2>
            <dl className="mt-3 space-y-1.5 font-mono text-[12px]">
              {Object.entries(catalog.build_ms).map(([k, v]) => (
                <div key={k} className="flex justify-between">
                  <dt className="text-ink-400">{k.replace("_ms", "")}</dt>
                  <dd className="tabular-nums text-ink-100">{v} ms</dd>
                </div>
              ))}
              <div className="flex justify-between border-t border-ink-800 pt-1.5">
                <dt className="text-ink-400">vector engine</dt>
                <dd className="text-ink-100">{catalog.vector_engine}</dd>
              </div>
            </dl>
            <p className="mt-3 text-[11.5px] leading-relaxed text-ink-400">
              The whole corpus is rebuilt from JSON on every boot. At this size that
              is faster and simpler than managing a persistent database.
            </p>
          </section>
        </div>
      ) : null}

      {!catalog && !error ? (
        <div className="rounded-xl border border-dashed border-ink-800 p-8 text-center text-[13px] text-ink-400">
          Loading the catalog…
        </div>
      ) : null}
    </main>
  );
}
