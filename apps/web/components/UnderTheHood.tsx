"use client";

import { useState } from "react";

import { CodeBlock } from "@/components/CodeBlock";
import { MODE_ACCENT, type SearchResponse } from "@/lib/api";

function Section({
  title,
  subtitle,
  children,
  defaultOpen = true,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className="border-b border-ink-800 last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3.5 py-2.5 text-left hover:bg-ink-900/50"
      >
        <span
          className={`text-ink-500 transition-transform ${open ? "rotate-90" : ""}`}
          aria-hidden
        >
          ▸
        </span>
        <span className="text-[12px] font-semibold uppercase tracking-widest text-ink-300">
          {title}
        </span>
        {subtitle ? (
          <span className="ml-auto font-mono text-[10.5px] text-ink-500">{subtitle}</span>
        ) : null}
      </button>
      {open ? <div className="space-y-3 px-3.5 pb-4">{children}</div> : null}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-ink-800 bg-ink-950/50 px-2.5 py-1.5">
      <div className="font-mono text-[10px] uppercase tracking-widest text-ink-500">
        {label}
      </div>
      <div className="mt-0.5 font-mono text-[12.5px] tabular-nums text-ink-100">{value}</div>
    </div>
  );
}

export function UnderTheHood({ data }: { data: SearchResponse }) {
  const accent = MODE_ACCENT[data.mode];
  const { plan, explain, fusion, ontology_trace: trace } = data;

  return (
    <div className="overflow-hidden rounded-xl border border-ink-800 bg-ink-900/40">
      <div
        className="border-b border-ink-800 px-3.5 py-2.5"
        style={{ background: `linear-gradient(90deg, ${accent}14, transparent 70%)` }}
      >
        <h2 className="text-[13px] font-semibold tracking-tight text-ink-100">
          Under the hood
        </h2>
        <p className="mt-0.5 text-[11.5px] text-ink-400">
          Every query below actually ran. Nothing here is illustrative.
        </p>
      </div>

      <Section title="1 · Query plan" subtitle={`${plan.latency_ms} ms`}>
        <p className="text-[12.5px] leading-relaxed text-ink-200">
          <span className="text-ink-500">Read as: </span>
          {plan.interpretation}
        </p>
        {plan.explanation ? (
          <p className="text-[12px] leading-relaxed text-ink-400">{plan.explanation}</p>
        ) : null}

        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Stat label="model" value={plan.model.replace("claude-", "")} />
          <Stat label="in / out tok" value={`${plan.input_tokens} / ${plan.output_tokens}`} />
          <Stat
            label="prompt cache"
            value={
              plan.cache_read_tokens
                ? `${plan.cache_read_tokens} read`
                : plan.cache_write_tokens
                  ? `${plan.cache_write_tokens} written`
                  : "—"
            }
          />
          <Stat label="plan" value={plan.cached ? "cached" : "fresh"} />
        </div>

        {plan.entities.length ? (
          <div className="flex flex-wrap gap-1.5">
            {plan.entities.map((e, i) => (
              <span
                key={i}
                className="rounded border border-ink-700 bg-ink-950/60 px-1.5 py-0.5 font-mono text-[10.5px] text-ink-300"
              >
                {e.text}
                <span className="text-ink-500"> · {e.kind}</span>
                {e.resolved_id ? <span className="text-emerald-400"> → {e.resolved_id}</span> : null}
              </span>
            ))}
          </div>
        ) : null}

        {plan.repaired ? (
          <p className="rounded-lg border border-amber-500/25 bg-amber-500/5 px-2.5 py-1.5 text-[11.5px] text-amber-200">
            The first Cypher attempt was rejected by Kuzu and repaired on a second
            pass. Both attempts are shown below.
          </p>
        ) : null}
      </Section>

      {trace ? (
        <Section
          title="2 · Ontology expansion"
          subtitle={`${trace.matched_phrases.length} phrases · ${trace.expanded_classes.length} classes`}
        >
          {trace.matched_phrases.length === 0 ? (
            <p className="text-[12px] text-ink-400">
              Nothing in this question matched the ontology, so this mode is behaving
              exactly like plain hybrid.
            </p>
          ) : (
            <>
              <ul className="space-y-1.5">
                {trace.matched_phrases.map((m, i) => (
                  <li
                    key={i}
                    className="flex flex-wrap items-baseline gap-x-2 rounded-lg border border-ink-800 bg-ink-950/50 px-2.5 py-1.5 font-mono text-[11.5px]"
                  >
                    <span className="text-arena-ontology">&quot;{m.phrase}&quot;</span>
                    <span className="text-ink-500">→</span>
                    <span className="text-ink-100">
                      hoops:{m.resolved_to}
                    </span>
                    {m.equivalent_to ? (
                      <span className="text-ink-400">≡ {m.equivalent_to}</span>
                    ) : null}
                    {m.graph_rel ? (
                      <span className="text-arena-graph">[:{m.graph_rel}]</span>
                    ) : null}
                    {m.derived ? (
                      <span className="rounded bg-violet-500/10 px-1 text-[9.5px] uppercase tracking-wider text-violet-300">
                        derived
                      </span>
                    ) : null}
                  </li>
                ))}
              </ul>

              {trace.sql_predicates.length ? (
                <div>
                  <div className="mb-1 font-mono text-[10px] uppercase tracking-widest text-ink-500">
                    became structured predicates
                  </div>
                  <CodeBlock
                    code={trace.sql_predicates.join("\nAND ")}
                    language="sql"
                    accent={accent}
                    dense
                  />
                </div>
              ) : null}

              {trace.turtle ? (
                <details className="rounded-lg border border-ink-800 bg-ink-950/50">
                  <summary className="cursor-pointer px-2.5 py-1.5 font-mono text-[10.5px] uppercase tracking-widest text-ink-500 hover:text-ink-300">
                    the axioms that fired (Turtle)
                  </summary>
                  <div className="p-2 pt-0">
                    <CodeBlock code={trace.turtle} language="text" accent={accent} dense />
                  </div>
                </details>
              ) : null}
            </>
          )}
        </Section>
      ) : null}

      <Section title={trace ? "3 · Queries executed" : "2 · Queries executed"}>
        <div className="space-y-3">
          {data.steps.map((step, i) => (
            <div key={i} className="space-y-1.5">
              <div className="flex flex-wrap items-baseline gap-x-2">
                <span className="text-[12px] font-medium text-ink-200">{step.label}</span>
                <span className="font-mono text-[10.5px] text-ink-500">
                  {step.engine}
                </span>
                <span className="ml-auto font-mono text-[10.5px] tabular-nums text-ink-500">
                  {step.row_count} rows · {step.latency_ms} ms
                </span>
              </div>
              <CodeBlock code={step.code} language={step.language} accent={accent} />
              {step.error ? (
                <p className="rounded-lg border border-rose-500/25 bg-rose-500/5 px-2.5 py-1.5 font-mono text-[11px] leading-relaxed text-rose-200">
                  {step.error}
                </p>
              ) : null}
              {step.note ? (
                <p className="text-[11.5px] leading-relaxed text-ink-400">{step.note}</p>
              ) : null}
              {step.table && step.table.rows.length > 0 ? (
                <div className="scroll-slim overflow-x-auto rounded-lg border border-ink-800">
                  <table className="w-full font-mono text-[11px]">
                    <thead>
                      <tr className="bg-ink-950/60 text-ink-500">
                        {step.table.columns.map((c) => (
                          <th key={c} className="whitespace-nowrap px-2 py-1 text-left font-normal">
                            {c}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {step.table.rows.slice(0, 12).map((row, ri) => (
                        <tr key={ri} className="border-t border-ink-800 text-ink-300">
                          {row.map((cell, ci) => (
                            <td key={ci} className="whitespace-nowrap px-2 py-1">
                              {cell === null ? (
                                <span className="text-ink-600">null</span>
                              ) : (
                                String(cell)
                              )}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}
            </div>
          ))}
        </div>
      </Section>

      {fusion ? (
        <Section title="Fusion" subtitle={fusion.method}>
          <CodeBlock code={fusion.formula} language="text" accent={accent} dense />
          <div className="flex flex-wrap gap-2">
            {Object.entries(fusion.legs).map(([leg, n]) => (
              <span
                key={leg}
                className="rounded-lg border border-ink-800 bg-ink-950/50 px-2 py-1 font-mono text-[11px] text-ink-300"
              >
                {leg}: {n} hits
                {fusion.weights?.[leg] ? (
                  <span className="text-ink-500"> · ×{fusion.weights[leg]}</span>
                ) : null}
              </span>
            ))}
          </div>
          <p className="text-[11.5px] leading-relaxed text-ink-400">{fusion.why}</p>
        </Section>
      ) : null}

      <Section title="What just happened">
        <p className="text-[12.5px] leading-relaxed text-ink-200">
          {explain.what_happened}
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <div className="mb-1.5 font-mono text-[10px] uppercase tracking-widest text-emerald-400">
              where this wins
            </div>
            <ul className="space-y-1">
              {explain.strengths.map((s, i) => (
                <li key={i} className="flex gap-1.5 text-[12px] leading-relaxed text-ink-300">
                  <span className="text-emerald-500">+</span>
                  <span>{s}</span>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <div className="mb-1.5 font-mono text-[10px] uppercase tracking-widest text-rose-400">
              where it breaks
            </div>
            <ul className="space-y-1">
              {explain.limits.map((s, i) => (
                <li key={i} className="flex gap-1.5 text-[12px] leading-relaxed text-ink-300">
                  <span className="text-rose-500">−</span>
                  <span>{s}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </Section>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-ink-800 px-3.5 py-2 font-mono text-[10.5px] text-ink-500">
        <span>plan {data.timings.plan_ms} ms</span>
        <span>retrieve {data.timings.retrieve_ms} ms</span>
        <span className="text-ink-300">total {data.timings.total_ms} ms</span>
      </div>
    </div>
  );
}
