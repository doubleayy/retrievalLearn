"use client";

import { API_URL, API_URL_CONFIGURED, diagnoseFetchFailure } from "@/lib/api";

/**
 * "Failed to fetch" tells you nothing. This shows which URL was attempted and
 * why it probably failed, because the three causes (unset build-time variable,
 * mixed content, CORS) are indistinguishable from the browser's error alone.
 */
export function ApiError({ error, title = "Could not reach the API" }: {
  error: unknown;
  title?: string;
}) {
  const message = error instanceof Error ? error.message : String(error);
  const hints = diagnoseFetchFailure(error);

  return (
    <div className="rounded-xl border border-rose-500/30 bg-rose-500/5 p-4">
      <p className="text-[13px] font-medium text-rose-200">{title}</p>
      <p className="mt-1 font-mono text-[12px] text-rose-300/90">{message}</p>

      <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-1 border-t border-rose-500/20 pt-2.5 font-mono text-[11.5px]">
        <div>
          <dt className="inline text-ink-500">tried: </dt>
          <dd className="inline text-ink-200">{API_URL}</dd>
        </div>
        <div>
          <dt className="inline text-ink-500">NEXT_PUBLIC_API_URL: </dt>
          <dd
            className={`inline ${API_URL_CONFIGURED ? "text-emerald-300" : "text-amber-300"}`}
          >
            {API_URL_CONFIGURED ? "set at build time" : "NOT SET — using fallback"}
          </dd>
        </div>
      </dl>

      {hints.length ? (
        <ul className="mt-3 space-y-1.5 border-t border-rose-500/20 pt-2.5">
          {hints.map((h, i) => (
            <li key={i} className="flex gap-1.5 text-[12px] leading-relaxed text-ink-300">
              <span className="text-rose-400">→</span>
              <span>{h}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
