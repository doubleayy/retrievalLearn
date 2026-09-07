"use client";

import { MODE_ACCENT, type ModeId, type ModeInfo } from "@/lib/api";

export function ModePicker({
  modes,
  value,
  onChange,
  disabled,
}: {
  modes: ModeInfo[];
  value: ModeId;
  onChange: (m: ModeId) => void;
  disabled?: boolean;
}) {
  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between">
        <h2 className="text-[11px] font-medium uppercase tracking-widest text-ink-400">
          Choose one retrieval type
        </h2>
        <span className="text-[11px] text-ink-500">one at a time — that is the point</span>
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        {modes.map((m) => {
          const active = m.id === value;
          const accent = MODE_ACCENT[m.id];
          return (
            <button
              key={m.id}
              type="button"
              disabled={disabled}
              onClick={() => onChange(m.id)}
              aria-pressed={active}
              className={`group relative overflow-hidden rounded-xl border p-3 text-left transition disabled:cursor-not-allowed disabled:opacity-60 ${
                active
                  ? "border-transparent bg-ink-850"
                  : "border-ink-800 bg-ink-900/50 hover:border-ink-700 hover:bg-ink-850/70"
              }`}
              style={active ? { boxShadow: `inset 0 0 0 1px ${accent}66` } : undefined}
            >
              <span
                className="absolute inset-x-0 top-0 h-[2px] transition-opacity"
                style={{ background: accent, opacity: active ? 1 : 0.2 }}
              />
              <div className="flex items-center gap-1.5">
                <span
                  className="h-1.5 w-1.5 shrink-0 rounded-full"
                  style={{ background: accent, opacity: active ? 1 : 0.45 }}
                />
                <span
                  className={`text-[13px] font-semibold leading-tight ${
                    active ? "text-ink-100" : "text-ink-200"
                  }`}
                >
                  {m.name}
                </span>
              </div>
              <p className="mt-1.5 text-[11px] leading-snug text-ink-400">{m.tagline}</p>
              <p
                className="mt-2 font-mono text-[10px] uppercase tracking-wide"
                style={{ color: active ? accent : "#6b7789" }}
              >
                {m.language}
              </p>
            </button>
          );
        })}
      </div>
      <p className="mt-2 text-[12px] text-ink-400">
        {modes.find((m) => m.id === value)?.one_liner}
      </p>
    </div>
  );
}
