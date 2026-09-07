"use client";

import { useState } from "react";

import type { ResultItem, SearchResponse } from "@/lib/api";

const KIND_STYLE: Record<string, { label: string; className: string }> = {
  article: { label: "article", className: "bg-sky-500/10 text-sky-300 ring-sky-500/25" },
  player: { label: "player", className: "bg-emerald-500/10 text-emerald-300 ring-emerald-500/25" },
  trade: { label: "trade", className: "bg-amber-500/10 text-amber-300 ring-amber-500/25" },
  path: { label: "graph row", className: "bg-violet-500/10 text-violet-300 ring-violet-500/25" },
};

function ScoreBadge({ item }: { item: ResultItem }) {
  const b = item.score_breakdown ?? {};
  let label = item.score.toFixed(4);
  let unit = "score";
  if (b.bm25_display !== undefined) {
    label = Number(b.bm25_display).toFixed(3);
    unit = "bm25";
  } else if (b.cosine_similarity !== undefined) {
    label = Number(b.cosine_similarity).toFixed(3);
    unit = "cosine";
  } else if (b.rrf) {
    label = Number(b.rrf.total).toFixed(5);
    unit = "rrf";
  } else if (item.kind === "player" || item.kind === "path") {
    label = "exact";
    unit = "match";
  }
  return (
    <div className="shrink-0 text-right">
      <div className="font-mono text-[13px] tabular-nums text-ink-100">{label}</div>
      <div className="font-mono text-[9px] uppercase tracking-widest text-ink-500">{unit}</div>
    </div>
  );
}

function Card({ item }: { item: ResultItem }) {
  const [open, setOpen] = useState(false);
  const kind = KIND_STYLE[item.kind] ?? KIND_STYLE.article;
  const note = item.data?.retrieval_note as string | undefined;
  const rrf = item.score_breakdown?.rrf;

  return (
    <li className="animate-fade-up rounded-xl border border-ink-800 bg-ink-900/50 p-3.5 transition hover:border-ink-700">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 w-5 shrink-0 text-right font-mono text-[12px] text-ink-500">
          {item.rank}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span
              className={`rounded px-1.5 py-px font-mono text-[9.5px] uppercase tracking-wider ring-1 ring-inset ${kind.className}`}
            >
              {kind.label}
            </span>
            {item.data?.conflict_kind ? (
              <span className="rounded bg-rose-500/10 px-1.5 py-px font-mono text-[9.5px] uppercase tracking-wider text-rose-300 ring-1 ring-inset ring-rose-500/25">
                {item.data.conflict_kind}
              </span>
            ) : null}
            {item.data?.published_at ? (
              <span className="font-mono text-[10px] text-ink-500">
                {item.data.published_at}
              </span>
            ) : null}
          </div>

          <h3 className="mt-1.5 text-[14px] font-medium leading-snug text-ink-100">
            {item.title}
          </h3>
          {item.snippet ? (
            <p className="mt-1 text-[12.5px] leading-relaxed text-ink-300">{item.snippet}</p>
          ) : null}

          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
            <p className="text-[11.5px] italic text-ink-400">{item.why}</p>
            <button
              type="button"
              onClick={() => setOpen((v) => !v)}
              className="font-mono text-[10px] uppercase tracking-wider text-ink-500 underline decoration-dotted underline-offset-2 hover:text-ink-300"
            >
              {open ? "hide scoring" : "scoring"}
            </button>
          </div>

          {open ? (
            <div className="mt-2 space-y-2 rounded-lg border border-ink-800 bg-ink-950/60 p-2.5">
              {rrf ? (
                <div>
                  <div className="mb-1 font-mono text-[10px] uppercase tracking-widest text-ink-500">
                    fusion contributions
                  </div>
                  <table className="w-full font-mono text-[11px]">
                    <tbody>
                      {Object.entries(rrf.sources as Record<string, any>).map(([leg, s]) => (
                        <tr key={leg} className="text-ink-300">
                          <td className="py-0.5 pr-3">{leg}</td>
                          <td className="py-0.5 pr-3 text-ink-500">rank {s.rank}</td>
                          <td className="py-0.5 pr-3 text-ink-500">×{s.weight ?? 1}</td>
                          <td className="py-0.5 text-right tabular-nums">
                            +{Number(s.contribution).toFixed(5)}
                          </td>
                        </tr>
                      ))}
                      <tr className="border-t border-ink-800 text-ink-100">
                        <td className="pt-1" colSpan={3}>
                          total
                        </td>
                        <td className="pt-1 text-right tabular-nums">
                          {Number(rrf.total).toFixed(5)}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              ) : (
                <pre className="scroll-slim overflow-x-auto font-mono text-[11px] text-ink-300">
                  {JSON.stringify(item.score_breakdown, null, 2)}
                </pre>
              )}
              {note ? (
                <div className="border-t border-ink-800 pt-2">
                  <div className="mb-1 font-mono text-[10px] uppercase tracking-widest text-ink-500">
                    why this document is in the corpus
                  </div>
                  <p className="text-[11.5px] leading-relaxed text-ink-300">{note}</p>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
        <ScoreBadge item={item} />
      </div>
    </li>
  );
}

export function ResultList({ data }: { data: SearchResponse }) {
  if (data.results.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-ink-700 bg-ink-900/40 p-6 text-center">
        <p className="text-[14px] font-medium text-ink-200">No results</p>
        <p className="mx-auto mt-1.5 max-w-md text-[12.5px] leading-relaxed text-ink-400">
          For keyword and graph search that is a real answer — the terms are not in
          the index, or the pattern does not match. Semantic search almost never
          returns nothing, which is its own kind of problem.
        </p>
      </div>
    );
  }

  return (
    <ul className="space-y-2.5">
      {data.results.map((r) => (
        <Card key={`${r.id}-${r.rank}`} item={r} />
      ))}
    </ul>
  );
}
