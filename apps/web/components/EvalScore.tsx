"use client";

import type { EvalRun } from "@/lib/api";

/**
 * Presentational atoms for the evaluation report.
 *
 * Colour is never the only carrier of meaning here: every score prints its
 * number and every grade prints its name, so the heatmap and the chips stay
 * readable without relying on hue discrimination.
 */

const SCORE_STEPS = [
  { min: 4.5, hue: "#4ade80", label: "solved" },
  { min: 3.5, hue: "#a3e635", label: "good" },
  { min: 2.0, hue: "#f5a524", label: "partial" },
  { min: 1.0, hue: "#fb923c", label: "poor" },
  { min: -1, hue: "#f87171", label: "failed" },
];

export function scoreTone(score: number) {
  return SCORE_STEPS.find((s) => score >= s.min) ?? SCORE_STEPS[SCORE_STEPS.length - 1];
}

export function ScorePill({ score, size = "md" }: { score: number; size?: "sm" | "md" | "lg" }) {
  const tone = scoreTone(score);
  const pad = size === "lg" ? "px-2.5 py-1 text-[18px]" : size === "sm" ? "px-1.5 py-px text-[11px]" : "px-2 py-0.5 text-[13px]";
  return (
    <span
      className={`inline-flex items-baseline gap-1 rounded-md font-mono font-semibold tabular-nums ${pad}`}
      style={{ background: `${tone.hue}1a`, color: tone.hue, border: `1px solid ${tone.hue}33` }}
    >
      {score.toFixed(1)}
      <span className="text-[0.7em] font-normal opacity-70">/5</span>
    </span>
  );
}

/** A 5-wide bar showing how the three components add up. */
export function ScoreBreakdown({ run }: { run: EvalRun }) {
  const c = run.components;
  const parts = [
    { id: "top_hit", label: "Top hit", value: c.top_hit, max: 2, hue: "#a78bfa" },
    { id: "coverage", label: "Coverage", value: c.coverage, max: 2, hue: "#22b8cf" },
    { id: "cleanliness", label: "Cleanliness", value: c.cleanliness, max: 1, hue: "#4ade80" },
  ];
  return (
    <div>
      <div className="flex h-2 w-full overflow-hidden rounded-full bg-ink-800">
        {parts.map((p) => (
          <div key={p.id} className="h-full" style={{ width: `${(p.max / 5) * 100}%` }}>
            <div
              className="h-full rounded-full"
              style={{ width: `${p.max ? (p.value / p.max) * 100 : 0}%`, background: p.hue }}
            />
          </div>
        ))}
      </div>
      <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-[10.5px] text-ink-400">
        {parts.map((p) => (
          <span key={p.id}>
            <span
              className="mr-1 inline-block h-1.5 w-1.5 rounded-full align-middle"
              style={{ background: p.hue }}
            />
            {p.label} {p.value.toFixed(1)}/{p.max.toFixed(1)}
          </span>
        ))}
      </div>
    </div>
  );
}

const GRADES: Record<number, { name: string; hue: string; bg: string }> = {
  3: { name: "answers", hue: "#4ade80", bg: "rgba(74,222,128,0.12)" },
  2: { name: "evidence", hue: "#22b8cf", bg: "rgba(34,184,207,0.12)" },
  1: { name: "topical", hue: "#f5a524", bg: "rgba(245,165,36,0.12)" },
  0: { name: "irrelevant", hue: "#6b7789", bg: "rgba(107,119,137,0.12)" },
  [-1]: { name: "trap", hue: "#f87171", bg: "rgba(248,113,113,0.14)" },
};

export function GradeChip({ grade, compact = false }: { grade: number; compact?: boolean }) {
  const g = GRADES[grade] ?? GRADES[0];
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded font-mono uppercase tracking-wider ${
        compact ? "px-1 py-px text-[9px]" : "px-1.5 py-0.5 text-[9.5px]"
      }`}
      style={{ background: g.bg, color: g.hue }}
    >
      {g.name}
    </span>
  );
}

export const GRADE_LEGEND = GRADES;
