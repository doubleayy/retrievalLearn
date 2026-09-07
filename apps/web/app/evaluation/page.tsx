"use client";

import { useEffect, useMemo, useState } from "react";

import { ApiError } from "@/components/ApiError";
import { CodeBlock } from "@/components/CodeBlock";
import { GradeChip, ScoreBreakdown, ScorePill, scoreTone } from "@/components/EvalScore";
import {
  getEval,
  MODE_ACCENT,
  MODE_ORDER,
  type EvalReport,
  type EvalRun,
  type EvalTest,
  type ModeId,
} from "@/lib/api";

export default function EvaluationPage() {
  const [report, setReport] = useState<EvalReport | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    getEval().then(setReport).catch(setError);
  }, []);

  if (error) {
    return (
      <main className="mx-auto max-w-[1400px] px-4 pb-16 pt-8 sm:px-6">
        <ApiError error={error} title="Could not load the evaluation report" />
      </main>
    );
  }

  if (!report) {
    return (
      <main className="mx-auto max-w-[1400px] px-4 pb-16 pt-8 sm:px-6">
        <div
          className="h-64 animate-shimmer rounded-xl border border-ink-800"
          style={{
            background: "linear-gradient(90deg, #12151d 25%, #1b202b 50%, #12151d 75%)",
            backgroundSize: "200% 100%",
          }}
        />
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-[1400px] px-4 pb-24 pt-8 sm:px-6">
      <Hero report={report} />
      <Leaderboard report={report} />
      <Matrix report={report} />
      <Rubric report={report} />

      <section className="mt-14">
        <SectionHeading
          eyebrow="the suite"
          title="Twelve questions, one at a time"
          blurb="Each test says why it is here before it says how anything scored. Pick a
                 mode to see the ranked page it produced and the query that produced it."
        />
        <div className="mt-6 space-y-5">
          {report.tests.map((test) => (
            <TestCard key={test.id} test={test} />
          ))}
        </div>
      </section>

      <Findings report={report} />
      <Caveats report={report} />
    </main>
  );
}

// --- page furniture -------------------------------------------------------

function SectionHeading({
  eyebrow,
  title,
  blurb,
}: {
  eyebrow: string;
  title: string;
  blurb?: string;
}) {
  return (
    <div className="max-w-3xl">
      <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-500">
        {eyebrow}
      </span>
      <h2 className="mt-1.5 text-[22px] font-semibold tracking-tight text-ink-100">{title}</h2>
      {blurb ? (
        <p className="mt-2 text-pretty text-[13.5px] leading-relaxed text-ink-300">{blurb}</p>
      ) : null}
    </div>
  );
}

function Hero({ report }: { report: EvalReport }) {
  const generated = new Date(report.generated_at);
  const meta = [
    ["generated", generated.toISOString().slice(0, 16).replace("T", " ") + " UTC"],
    ["plans", report.planner.source],
    ["retrievals", String(report.analysis.totals.retrievals)],
    ["judgments", String(report.analysis.totals.judgments)],
    ["engine", report.environment.vector_engine],
  ];

  return (
    <section className="mb-12">
      <h1 className="text-balance text-3xl font-semibold tracking-tight text-ink-100 sm:text-4xl">
        Which of these actually works?
      </h1>
      <p className="mt-3 max-w-3xl text-pretty text-[15px] leading-relaxed text-ink-300">
        Every retrieval mode, run against the same twelve questions, scored out of five
        against relevance judgments written by hand before the results were looked at.
        The questions were chosen because each one breaks something. Nothing here is
        computed when you load the page — this is a report, and everyone sees the same one.
      </p>

      <div className="mt-5 flex flex-wrap gap-x-5 gap-y-2 rounded-xl border border-ink-800 bg-ink-900/40 px-4 py-3">
        {meta.map(([k, v]) => (
          <div key={k}>
            <div className="font-mono text-[9.5px] uppercase tracking-[0.16em] text-ink-500">
              {k}
            </div>
            <div className="font-mono text-[12px] text-ink-200">{v}</div>
          </div>
        ))}
      </div>

      <p className="mt-3 max-w-3xl text-[12.5px] leading-relaxed text-ink-400">
        {report.planner.note} Regenerate it with{" "}
        <code className="rounded bg-ink-850 px-1.5 py-0.5 font-mono text-[11.5px] text-ink-200">
          {report.how_to_reproduce}
        </code>
        .
      </p>
    </section>
  );
}

// --- leaderboard ----------------------------------------------------------

function Leaderboard({ report }: { report: EvalReport }) {
  const rows = report.analysis.leaderboard;
  const max = Math.max(...rows.map((r) => r.mean), 5);

  return (
    <section className="mt-14">
      <SectionHeading
        eyebrow="overall"
        title="Mean score across the suite"
        blurb="Read this as a summary of the twelve questions below, not as a ranking of
               retrieval techniques. The mean moves with the question mix, and the
               question mix was chosen by hand."
      />
      <div className="mt-5 overflow-x-auto rounded-xl border border-ink-800 bg-ink-900/30">
        <table className="w-full min-w-[720px] border-collapse text-[13px]">
          <thead>
            <tr className="border-b border-ink-800 text-left font-mono text-[10px] uppercase tracking-wider text-ink-500">
              <th className="px-4 py-2.5 font-normal">Mode</th>
              <th className="px-4 py-2.5 font-normal">Mean</th>
              <th className="px-4 py-2.5 font-normal">Range</th>
              <th className="px-4 py-2.5 font-normal" title="Tests where this mode tied or beat every other; ties split">
                Wins
              </th>
              <th className="px-4 py-2.5 font-normal">Traps eaten</th>
              <th className="px-4 py-2.5 font-normal">Empty pages</th>
              <th className="px-4 py-2.5 font-normal">Median latency</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.mode} className="border-b border-ink-800/60 last:border-0">
                <td className="px-4 py-3">
                  <span className="flex items-center gap-2">
                    <span
                      className="inline-block h-2 w-2 shrink-0 rounded-full"
                      style={{ background: MODE_ACCENT[row.mode] }}
                    />
                    <span className="font-medium text-ink-100">{row.label}</span>
                  </span>
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2.5">
                    <ScorePill score={row.mean} size="sm" />
                    <span className="hidden h-1.5 w-28 overflow-hidden rounded-full bg-ink-800 sm:block">
                      <span
                        className="block h-full rounded-full"
                        style={{
                          width: `${(row.mean / max) * 100}%`,
                          background: scoreTone(row.mean).hue,
                        }}
                      />
                    </span>
                  </div>
                </td>
                <td className="px-4 py-3 font-mono tabular-nums text-ink-300">
                  {row.worst.toFixed(1)} – {row.best.toFixed(1)}
                </td>
                <td className="px-4 py-3 font-mono tabular-nums text-ink-300">{row.wins}</td>
                <td className="px-4 py-3 font-mono tabular-nums">
                  <span className={row.traps_retrieved ? "text-red-300" : "text-ink-500"}>
                    {row.traps_retrieved}
                  </span>
                </td>
                <td className="px-4 py-3 font-mono tabular-nums text-ink-300">
                  {row.empty_answers}
                </td>
                <td className="px-4 py-3 font-mono tabular-nums text-ink-300">
                  {row.median_latency_ms} ms
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// --- matrix ---------------------------------------------------------------

function Matrix({ report }: { report: EvalReport }) {
  return (
    <section className="mt-14">
      <SectionHeading
        eyebrow="every cell"
        title="Sixty retrievals"
        blurb="Twelve questions down, five modes across. The interesting thing about this
               grid is how little of it is uniform: the winner changes from row to row,
               one row has no good answer from anything, and the two modes most people
               mean by 'search' occupy the bottom two columns."
      />

      <div className="mt-5 overflow-x-auto rounded-xl border border-ink-800 bg-ink-900/30">
        <table className="w-full min-w-[760px] border-collapse text-[12.5px]">
          <thead>
            <tr className="border-b border-ink-800 text-left font-mono text-[10px] uppercase tracking-wider text-ink-500">
              <th className="px-4 py-2.5 font-normal">Question</th>
              {report.modes.map((m) => (
                <th key={m.id} className="px-3 py-2.5 text-center font-normal">
                  <span
                    className="mr-1 inline-block h-1.5 w-1.5 rounded-full align-middle"
                    style={{ background: MODE_ACCENT[m.id] }}
                  />
                  {m.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {report.tests.map((test) => (
              <tr key={test.id} className="border-b border-ink-800/60 last:border-0">
                <td className="px-4 py-2">
                  <a
                    href={`#${test.id}`}
                    className="block max-w-[300px] truncate text-ink-200 transition hover:text-ink-100"
                    title={test.query}
                  >
                    {test.query}
                  </a>
                  <span className="font-mono text-[10px] text-ink-500">{test.family}</span>
                </td>
                {report.modes.map((m) => {
                  const score = test.runs[m.id].score;
                  const tone = scoreTone(score);
                  const isBest = test.best_mode.includes(m.id);
                  return (
                    <td key={m.id} className="px-3 py-2 text-center">
                      <a
                        href={`#${test.id}`}
                        className="inline-flex h-8 w-14 items-center justify-center rounded-md font-mono text-[13px] font-semibold tabular-nums transition hover:brightness-125"
                        style={{
                          background: `${tone.hue}${score >= 4.5 ? "26" : "14"}`,
                          color: tone.hue,
                          boxShadow: isBest ? `inset 0 0 0 1px ${tone.hue}66` : undefined,
                        }}
                        title={`${test.query} — ${m.label}: ${score}/5`}
                      >
                        {score.toFixed(1)}
                      </a>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3 className="mt-6 font-mono text-[10px] uppercase tracking-[0.18em] text-ink-500">
        The same grid, averaged by what each question is testing
      </h3>
      <div className="mt-2 overflow-x-auto rounded-xl border border-ink-800 bg-ink-900/30">
        <table className="w-full min-w-[760px] border-collapse text-[12.5px]">
          <tbody>
            {report.analysis.by_family.map((row) => (
              <tr key={row.family} className="border-b border-ink-800/60 last:border-0">
                <td className="px-4 py-2.5">
                  <div className="text-ink-200">{row.family}</div>
                  <div className="max-w-[420px] text-[11.5px] leading-relaxed text-ink-500">
                    {row.blurb}
                  </div>
                </td>
                {MODE_ORDER.map((m) => {
                  const value = row.scores[m];
                  return (
                    <td key={m} className="px-3 py-2.5 text-center">
                      <span
                        className="font-mono tabular-nums"
                        style={{ color: scoreTone(value).hue }}
                      >
                        {value.toFixed(2)}
                      </span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// --- rubric ---------------------------------------------------------------

function Rubric({ report }: { report: EvalReport }) {
  const r = report.rubric;
  return (
    <section className="mt-14">
      <SectionHeading
        eyebrow="the rubric"
        title="Where the five points come from"
        blurb="Deliberately arithmetic rather than a standard IR metric. nDCG is the right
               tool for comparing two rankers, and it is opaque to anyone who has not met
               it. Three components that visibly add up to five can be argued with, which
               is the point."
      />

      <div className="mt-5 grid gap-3 md:grid-cols-3">
        {r.components.map((c) => (
          <div key={c.id} className="rounded-xl border border-ink-800 bg-ink-900/40 p-4">
            <div className="flex items-baseline justify-between">
              <h3 className="text-[14px] font-semibold text-ink-100">{c.name}</h3>
              <span className="font-mono text-[11px] text-ink-400">
                0 – {c.max.toFixed(1)}
              </span>
            </div>
            <p className="mt-2 font-mono text-[11.5px] leading-relaxed text-ink-300">{c.how}</p>
            <p className="mt-2 text-[12.5px] leading-relaxed text-ink-400">{c.why}</p>
          </div>
        ))}
      </div>

      <div className="mt-3 rounded-xl border border-ink-800 bg-ink-900/40 p-4">
        <h3 className="text-[13px] font-semibold text-ink-100">Relevance grades</h3>
        <p className="mt-1.5 text-[12.5px] leading-relaxed text-ink-400">
          Judged against the question, not against any mode. A player is a correct answer
          to “which players…?” even though only the graph modes can return one — that
          asymmetry is a finding, not a scoring bug.
        </p>
        <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {r.grades.map((g) => (
            <div key={g.grade} className="flex items-start gap-2">
              <GradeChip grade={g.grade} />
              <span className="text-[12px] leading-relaxed text-ink-300">{g.meaning}</span>
            </div>
          ))}
        </div>
        <p className="mt-3 border-t border-ink-800 pt-3 font-mono text-[11.5px] text-ink-400">
          k = {r.k} · noise window = top {r.noise_window} · {r.rounding} · {r.empty_rule}
        </p>
      </div>
    </section>
  );
}

// --- one test -------------------------------------------------------------

function TestCard({ test }: { test: EvalTest }) {
  const [mode, setMode] = useState<ModeId>(test.best_mode[0] ?? "keyword");
  const [showJudgments, setShowJudgments] = useState(false);
  const run = test.runs[mode];

  return (
    <article
      id={test.id}
      className="scroll-mt-20 overflow-hidden rounded-2xl border border-ink-800 bg-ink-900/30"
    >
      {/* header ------------------------------------------------------- */}
      <div className="border-b border-ink-800 p-5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded bg-ink-800 px-1.5 py-0.5 font-mono text-[9.5px] uppercase tracking-wider text-ink-300">
            {test.family}
          </span>
          <span className="font-mono text-[10.5px] text-ink-500">{test.id}</span>
          <span className="ml-auto font-mono text-[10.5px] text-ink-500">
            spread {test.spread.toFixed(1)} points
          </span>
        </div>

        <h3 className="mt-2.5 text-[19px] font-semibold tracking-tight text-ink-100">
          {test.headline}
        </h3>
        <p className="mt-1.5 font-mono text-[13.5px] text-arena-ontology">“{test.query}”</p>

        <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
          <div>
            <h4 className="font-mono text-[9.5px] uppercase tracking-[0.16em] text-ink-500">
              Why this question is in the suite
            </h4>
            <p className="mt-1.5 text-pretty text-[13px] leading-relaxed text-ink-300">
              {test.preamble}
            </p>
          </div>
          <div className="rounded-lg border border-ink-800 bg-ink-950/50 p-3.5">
            <h4 className="font-mono text-[9.5px] uppercase tracking-[0.16em] text-ink-500">
              What a good answer looks like
            </h4>
            <p className="mt-1.5 text-[12.5px] leading-relaxed text-ink-300">
              {test.what_good_looks_like}
            </p>
          </div>
        </div>

        {test.traps.length ? (
          <div className="mt-3 space-y-1.5">
            {test.traps.map((trap) => (
              <div
                key={trap.id}
                className="flex gap-2 rounded-lg border border-red-500/15 bg-red-500/[0.04] px-3 py-2"
              >
                <GradeChip grade={-1} />
                <div>
                  <span className="text-[12.5px] font-medium text-ink-200">{trap.title}</span>
                  <p className="mt-0.5 text-[12px] leading-relaxed text-ink-400">
                    {trap.reason}
                  </p>
                </div>
              </div>
            ))}
          </div>
        ) : null}

        <button
          type="button"
          onClick={() => setShowJudgments((v) => !v)}
          className="mt-3 rounded-md border border-ink-800 px-2.5 py-1 font-mono text-[11px] text-ink-400 transition hover:border-ink-600 hover:text-ink-200"
        >
          {showJudgments ? "hide" : "show"} the {test.gold.length} relevance judgments
        </button>
        {showJudgments ? (
          <div className="mt-2.5 flex flex-wrap gap-1.5 rounded-lg border border-ink-800 bg-ink-950/50 p-3">
            {test.gold.map((g) => (
              <span
                key={g.id}
                className="inline-flex items-center gap-1.5 rounded border border-ink-800 bg-ink-900/60 px-1.5 py-0.5"
              >
                <GradeChip grade={g.grade} compact />
                <span className="text-[11.5px] text-ink-300">{g.title}</span>
              </span>
            ))}
          </div>
        ) : null}
      </div>

      {/* mode tabs ---------------------------------------------------- */}
      <div className="flex flex-wrap gap-1.5 border-b border-ink-800 bg-ink-950/40 px-5 py-3">
        {MODE_ORDER.map((m) => {
          const r = test.runs[m];
          const active = m === mode;
          const tone = scoreTone(r.score);
          return (
            <button
              key={m}
              type="button"
              onClick={() => setMode(m)}
              className={`flex items-center gap-2 rounded-lg border px-2.5 py-1.5 transition ${
                active
                  ? "border-ink-600 bg-ink-800/70"
                  : "border-ink-800 bg-transparent hover:border-ink-700"
              }`}
            >
              <span
                className="inline-block h-1.5 w-1.5 rounded-full"
                style={{ background: MODE_ACCENT[m] }}
              />
              <span
                className={`font-mono text-[11.5px] ${active ? "text-ink-100" : "text-ink-400"}`}
              >
                {m}
              </span>
              <span
                className="font-mono text-[12px] font-semibold tabular-nums"
                style={{ color: tone.hue }}
              >
                {r.score.toFixed(1)}
              </span>
            </button>
          );
        })}
      </div>

      <ModeReport test={test} run={run} mode={mode} />
    </article>
  );
}

function ModeReport({ test, run, mode }: { test: EvalTest; run: EvalRun; mode: ModeId }) {
  const c = run.components;
  return (
    <div className="grid items-start gap-5 p-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      {/* left: what it retrieved ------------------------------------- */}
      <div>
        <div className="mb-3 flex items-center gap-3">
          <ScorePill score={run.score} size="lg" />
          <div className="min-w-0 flex-1">
            <ScoreBreakdown run={run} />
          </div>
        </div>

        <p className="mb-3 rounded-lg border border-ink-800 bg-ink-950/50 px-3 py-2 text-[12.5px] leading-relaxed text-ink-300">
          {run.verdict}
        </p>

        {run.results.length ? (
          <ol className="space-y-1.5">
            {run.results.map((r) => (
              <li
                key={`${r.rank}-${r.id}`}
                className="rounded-lg border border-ink-800 bg-ink-900/40 px-3 py-2"
                style={
                  r.grade === -1
                    ? { borderColor: "rgba(248,113,113,0.28)" }
                    : r.grade === 3
                      ? { borderColor: "rgba(74,222,128,0.24)" }
                      : undefined
                }
              >
                <div className="flex items-baseline gap-2">
                  <span className="font-mono text-[11px] tabular-nums text-ink-500">
                    {r.rank}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-[13px] text-ink-100">
                    {r.title}
                  </span>
                  <GradeChip grade={r.grade} />
                </div>
                <div className="mt-0.5 flex items-baseline gap-2 font-mono text-[10.5px] text-ink-500">
                  <span>{r.id}</span>
                  <span>score {r.score}</span>
                </div>
                {r.trap_reason ? (
                  <p className="mt-1 text-[11.5px] leading-relaxed text-red-300/80">
                    {r.trap_reason}
                  </p>
                ) : r.snippet ? (
                  <p className="mt-1 line-clamp-2 text-[11.5px] leading-relaxed text-ink-400">
                    {r.snippet}
                  </p>
                ) : null}
              </li>
            ))}
          </ol>
        ) : (
          <div className="rounded-lg border border-dashed border-ink-700 bg-ink-950/40 px-3 py-6 text-center">
            <p className="text-[13px] text-ink-300">Nothing returned.</p>
            <p className="mt-1 text-[12px] text-ink-500">
              Scored zero. Silence is not precision.
            </p>
          </div>
        )}

        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[10.5px] text-ink-500">
          <span>retrieved {c.retrieved}</span>
          <span>
            answers {c.answers_found}/{c.answers_possible}
          </span>
          <span>first correct at rank {c.first_answer_rank ?? "—"}</span>
          <span className={c.traps_hit ? "text-red-300/80" : undefined}>
            traps {c.traps_hit}
          </span>
          <span>{run.latency_ms} ms</span>
        </div>
      </div>

      {/* right: why, and what ran ------------------------------------ */}
      <div className="space-y-3">
        {run.commentary ? (
          <div className="rounded-lg border-l-2 bg-ink-900/40 py-2.5 pl-3.5 pr-3"
               style={{ borderLeftColor: MODE_ACCENT[mode] }}>
            <h4 className="font-mono text-[9.5px] uppercase tracking-[0.16em] text-ink-500">
              What is happening here
            </h4>
            <p className="mt-1.5 text-pretty text-[12.5px] leading-relaxed text-ink-300">
              {run.commentary}
            </p>
          </div>
        ) : null}

        {run.warnings.map((w, i) => (
          <p
            key={i}
            className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-2.5 py-1.5 text-[11.5px] leading-relaxed text-amber-200/90"
          >
            {w}
          </p>
        ))}

        {test.plan.plan_note ? (
          <p className="rounded-lg border border-ink-800 bg-ink-950/50 px-3 py-2 text-[11.5px] leading-relaxed text-ink-400">
            <span className="font-mono text-[10px] uppercase tracking-wider text-ink-500">
              on this plan ·{" "}
            </span>
            {test.plan.plan_note}
          </p>
        ) : null}

        <div className="space-y-2.5">
          {run.steps.map((step, i) => (
            <div key={i}>
              <div className="mb-1 flex items-baseline justify-between gap-2">
                <span className="text-[11.5px] text-ink-300">{step.label}</span>
                <span className="shrink-0 font-mono text-[10px] text-ink-500">
                  {step.row_count} rows · {step.latency_ms} ms
                </span>
              </div>
              <CodeBlock code={step.code} language={step.language} accent={MODE_ACCENT[mode]} dense />
              {step.error ? (
                <p className="mt-1 rounded border border-red-500/20 bg-red-500/5 px-2 py-1 font-mono text-[11px] text-red-300">
                  {step.error}
                </p>
              ) : null}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// --- findings -------------------------------------------------------------

function Findings({ report }: { report: EvalReport }) {
  const titleFor = useMemo(() => {
    const map = new Map(report.tests.map((t) => [t.id, t.query]));
    return (id: string) => map.get(id) ?? id;
  }, [report.tests]);

  return (
    <section className="mt-16">
      <SectionHeading
        eyebrow="analysis"
        title="What the sixty runs actually show"
        blurb="The prose below is fixed; every number in it is interpolated from the run
               that produced this report. A conclusion that stops being true will read as
               obviously wrong rather than quietly going stale."
      />
      <div className="mt-6 space-y-4">
        {report.analysis.findings.map((f, i) => (
          <div key={f.title} className="rounded-xl border border-ink-800 bg-ink-900/30 p-5">
            <div className="flex items-baseline gap-3">
              <span className="font-mono text-[11px] tabular-nums text-ink-600">
                {String(i + 1).padStart(2, "0")}
              </span>
              <h3 className="text-balance text-[16px] font-semibold tracking-tight text-ink-100">
                {f.title}
              </h3>
            </div>
            <p className="mt-2.5 max-w-4xl text-pretty pl-8 text-[13.5px] leading-relaxed text-ink-300">
              {f.body}
            </p>
            {f.evidence.length ? (
              <div className="mt-3 flex flex-wrap items-center gap-1.5 pl-8">
                <span className="font-mono text-[10px] uppercase tracking-wider text-ink-500">
                  see
                </span>
                {f.evidence.map((id) => (
                  <a
                    key={id}
                    href={`#${id}`}
                    className="rounded-full border border-ink-800 bg-ink-900/50 px-2.5 py-0.5 text-[11.5px] text-ink-300 transition hover:border-ink-600 hover:text-ink-100"
                  >
                    {titleFor(id)}
                  </a>
                ))}
              </div>
            ) : null}
          </div>
        ))}
      </div>
    </section>
  );
}

function Caveats({ report }: { report: EvalReport }) {
  return (
    <section className="mt-14">
      <SectionHeading
        eyebrow="read this last"
        title="What this report is not"
      />
      <ul className="mt-5 space-y-2.5">
        {report.caveats.map((c, i) => (
          <li
            key={i}
            className="flex gap-3 rounded-xl border border-ink-800 bg-ink-900/20 px-4 py-3"
          >
            <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-ink-600" />
            <span className="text-pretty text-[13px] leading-relaxed text-ink-300">{c}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
