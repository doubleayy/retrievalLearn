"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ModePicker } from "@/components/ModePicker";
import { ResultList } from "@/components/ResultList";
import { UnderTheHood } from "@/components/UnderTheHood";
import {
  getExamples,
  getModes,
  MODE_ACCENT,
  MODE_ORDER,
  search,
  type ExampleQuery,
  type ModeId,
  type ModeInfo,
  type SearchResponse,
} from "@/lib/api";

const FALLBACK_MODES: ModeInfo[] = MODE_ORDER.map((id) => ({
  id,
  name: id,
  tagline: "",
  language: "",
  one_liner: "",
}));

export default function ArenaPage() {
  const [modes, setModes] = useState<ModeInfo[]>(FALLBACK_MODES);
  const [examples, setExamples] = useState<ExampleQuery[]>([]);
  const [mode, setMode] = useState<ModeId>("keyword");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [runs, setRuns] = useState<Partial<Record<ModeId, SearchResponse>>>({});
  const [activeExample, setActiveExample] = useState<ExampleQuery | null>(null);
  const lastQuery = useRef("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    getModes()
      .then((d) => setModes(d.modes))
      .catch(() => undefined);
    getExamples()
      .then((d) => setExamples(d.examples))
      .catch(() => undefined);
  }, []);

  const run = useCallback(
    async (q: string, m: ModeId) => {
      const text = q.trim();
      if (!text) return;
      setLoading(true);
      setError("");
      if (text !== lastQuery.current) {
        setRuns({});
        lastQuery.current = text;
      }
      try {
        const data = await search(text, m);
        setRuns((prev) => ({ ...prev, [m]: data }));
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  const current = runs[mode];
  const ranModes = MODE_ORDER.filter((m) => runs[m]);

  return (
    <main className="mx-auto max-w-[1400px] px-4 pb-16 pt-8 sm:px-6">
      <section className="mb-8 max-w-3xl">
        <h1 className="text-balance text-3xl font-semibold tracking-tight text-ink-100 sm:text-4xl">
          See how machines find things.
        </h1>
        <p className="mt-3 text-pretty text-[15px] leading-relaxed text-ink-300">
          Five ways to search the same corpus of basketball players, trades and
          news. Pick one, ask a question, and watch the actual SQL or Cypher that
          runs — plus where that approach quietly falls apart.
        </p>
      </section>

      <div className="mb-6">
        <ModePicker modes={modes} value={mode} onChange={setMode} disabled={loading} />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          run(query, mode);
        }}
        className="mb-3"
      >
        <div className="flex flex-col gap-2 sm:flex-row">
          <div className="relative flex-1">
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              maxLength={300}
              placeholder="which big men have beef with a former teammate?"
              className="w-full rounded-xl border border-ink-700 bg-ink-900/70 px-4 py-3 text-[14px] text-ink-100 placeholder:text-ink-500 focus:border-ink-500 focus:outline-none focus:ring-2 focus:ring-ink-600/40"
            />
          </div>
          <button
            type="submit"
            disabled={loading || !query.trim()}
            className="rounded-xl px-6 py-3 text-[14px] font-semibold text-ink-950 transition disabled:cursor-not-allowed disabled:opacity-40"
            style={{ background: MODE_ACCENT[mode] }}
          >
            {loading ? "Running…" : "Run query"}
          </button>
        </div>
      </form>

      {examples.length ? (
        <div className="mb-6">
          <div className="flex flex-wrap gap-1.5">
            {examples.map((ex) => (
              <button
                key={ex.id}
                type="button"
                onClick={() => {
                  setQuery(ex.query);
                  setActiveExample(ex);
                  if (ex.try_modes.length) setMode(ex.try_modes[0]);
                  run(ex.query, ex.try_modes[0] ?? mode);
                }}
                className="rounded-full border border-ink-800 bg-ink-900/50 px-3 py-1 text-[12px] text-ink-300 transition hover:border-ink-600 hover:text-ink-100"
              >
                {ex.query}
              </button>
            ))}
          </div>
          {activeExample ? (
            <div className="mt-3 rounded-xl border border-ink-800 bg-ink-900/40 p-3.5">
              <div className="flex items-baseline gap-2">
                <span className="rounded bg-arena-ontology/15 px-1.5 py-px font-mono text-[9.5px] uppercase tracking-wider text-arena-ontology">
                  lesson
                </span>
                <span className="text-[13px] font-medium text-ink-100">
                  {activeExample.headline}
                </span>
              </div>
              <p className="mt-1.5 text-[12.5px] leading-relaxed text-ink-300">
                {activeExample.lesson}
              </p>
              <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                <span className="text-[11.5px] text-ink-500">Run it in:</span>
                {activeExample.try_modes.map((m) => (
                  <button
                    key={m}
                    type="button"
                    disabled={loading}
                    onClick={() => {
                      setMode(m);
                      run(activeExample.query, m);
                    }}
                    className={`rounded-md border px-2 py-0.5 font-mono text-[11px] transition disabled:opacity-50 ${
                      runs[m] ? "border-ink-600 text-ink-200" : "border-ink-800 text-ink-400"
                    } hover:border-ink-500 hover:text-ink-100`}
                    style={runs[m] ? { borderColor: `${MODE_ACCENT[m]}66` } : undefined}
                  >
                    {m}
                    {runs[m] ? (
                      <span className="text-ink-500"> · {runs[m]!.results.length}</span>
                    ) : null}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}

      {error ? (
        <div className="mb-6 rounded-xl border border-rose-500/30 bg-rose-500/5 p-3.5">
          <p className="text-[13px] font-medium text-rose-200">Query failed</p>
          <p className="mt-1 text-[12.5px] leading-relaxed text-rose-300/90">{error}</p>
        </div>
      ) : null}

      {ranModes.length > 1 ? (
        <div className="mb-4 flex flex-wrap items-center gap-2 rounded-xl border border-ink-800 bg-ink-900/30 px-3 py-2">
          <span className="text-[11.5px] text-ink-500">
            Same question, different modes:
          </span>
          {ranModes.map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMode(m)}
              className={`rounded-md px-2 py-0.5 font-mono text-[11px] transition ${
                m === mode ? "bg-ink-800 text-ink-100" : "text-ink-400 hover:text-ink-200"
              }`}
            >
              <span
                className="mr-1.5 inline-block h-1.5 w-1.5 rounded-full align-middle"
                style={{ background: MODE_ACCENT[m] }}
              />
              {m} · {runs[m]!.results.length} results · {runs[m]!.timings.total_ms} ms
            </button>
          ))}
        </div>
      ) : null}

      {loading && !current ? (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          {[0, 1].map((i) => (
            <div
              key={i}
              className="h-64 animate-shimmer rounded-xl border border-ink-800"
              style={{
                background:
                  "linear-gradient(90deg, #12151d 25%, #1b202b 50%, #12151d 75%)",
                backgroundSize: "200% 100%",
              }}
            />
          ))}
        </div>
      ) : null}

      {current ? (
        <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <div>
            <div className="mb-2.5 flex items-baseline justify-between">
              <h2 className="text-[13px] font-semibold uppercase tracking-widest text-ink-300">
                Results
              </h2>
              <span className="font-mono text-[11px] text-ink-500">
                {current.results.length} shown
              </span>
            </div>
            {current.warnings.length ? (
              <div className="mb-2.5 space-y-1.5">
                {current.warnings.map((w, i) => (
                  <p
                    key={i}
                    className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-2.5 py-1.5 text-[11.5px] leading-relaxed text-amber-200/90"
                  >
                    {w}
                  </p>
                ))}
              </div>
            ) : null}
            <ResultList data={current} />
          </div>
          <UnderTheHood data={current} />
        </div>
      ) : null}

      {!current && !loading ? (
        <div className="rounded-xl border border-dashed border-ink-800 bg-ink-900/20 p-8 text-center">
          <p className="text-[14px] text-ink-300">
            Pick a mode, then ask something — or start with one of the example
            questions above.
          </p>
          <p className="mx-auto mt-2 max-w-lg text-[12.5px] leading-relaxed text-ink-500">
            The examples are chosen because they break at least one of the five
            approaches. Run the same question in two modes to see the difference.
          </p>
        </div>
      ) : null}
    </main>
  );
}
