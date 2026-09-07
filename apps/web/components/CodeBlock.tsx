"use client";

import { useMemo, useState } from "react";

const KEYWORDS = [
  "SELECT", "FROM", "WHERE", "JOIN", "LEFT", "INNER", "ON", "ORDER", "BY", "GROUP",
  "LIMIT", "OFFSET", "AND", "OR", "NOT", "IN", "AS", "DESC", "ASC", "IS", "NULL",
  "MATCH", "OPTIONAL", "RETURN", "DISTINCT", "WITH", "UNWIND", "COUNT", "CREATE",
  "NEAR", "INSERT", "INTO", "VALUES", "CASE", "WHEN", "THEN", "ELSE", "END",
];

const FUNCTIONS = [
  "bm25", "snippet", "vec_distance_cosine", "count", "collect", "lower", "contains",
  "TextEmbedding", "query_embed", "argsort", "next", "numpy",
];

type Token = { text: string; cls?: string };

const PATTERN = new RegExp(
  [
    "(--[^\\n]*|#[^\\n]*)", // 1 comment
    "('(?:[^'\\\\]|\\\\.)*'|\"(?:[^\"\\\\]|\\\\.)*\")", // 2 string
    "(\\[:[A-Z_]+\\]|:[A-Z][A-Z_]{2,})", // 3 cypher relationship / label
    "(\\b\\d+(?:\\.\\d+)?\\b)", // 4 number
    `\\b(${KEYWORDS.join("|")})\\b`, // 5 keyword
    `\\b(${FUNCTIONS.join("|")})\\b`, // 6 function
  ].join("|"),
  "gi",
);

function tokenize(code: string): Token[] {
  const out: Token[] = [];
  let last = 0;
  PATTERN.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = PATTERN.exec(code)) !== null) {
    if (m.index > last) out.push({ text: code.slice(last, m.index) });
    const cls = m[1]
      ? "tok-com"
      : m[2]
        ? "tok-str"
        : m[3]
          ? "tok-rel"
          : m[4]
            ? "tok-num"
            : m[5]
              ? "tok-kw"
              : "tok-fn";
    out.push({ text: m[0], cls });
    last = m.index + m[0].length;
    if (m[0].length === 0) PATTERN.lastIndex++;
  }
  if (last < code.length) out.push({ text: code.slice(last) });
  return out;
}

const LANG_LABEL: Record<string, string> = {
  sql: "SQL",
  cypher: "Cypher",
  python: "Python",
  text: "trace",
  json: "JSON",
};

export function CodeBlock({
  code,
  language = "sql",
  accent = "#6b7789",
  dense = false,
}: {
  code: string;
  language?: string;
  accent?: string;
  dense?: boolean;
}) {
  const [copied, setCopied] = useState(false);
  const tokens = useMemo(
    () => (language === "text" ? [{ text: code }] : tokenize(code)),
    [code, language],
  );

  if (!code?.trim()) {
    return (
      <div className="rounded-lg border border-dashed border-ink-700 bg-ink-900/60 px-3 py-4 text-xs text-ink-400">
        (nothing to show)
      </div>
    );
  }

  return (
    <div className="group relative overflow-hidden rounded-lg border border-ink-700 bg-ink-950/80">
      <div className="flex items-center justify-between border-b border-ink-800 px-3 py-1.5">
        <span
          className="font-mono text-[10px] uppercase tracking-widest"
          style={{ color: accent }}
        >
          {LANG_LABEL[language] ?? language}
        </span>
        <button
          type="button"
          onClick={() => {
            navigator.clipboard?.writeText(code);
            setCopied(true);
            setTimeout(() => setCopied(false), 1200);
          }}
          className="rounded px-1.5 py-0.5 font-mono text-[10px] text-ink-400 opacity-0 transition hover:bg-ink-800 hover:text-ink-100 focus:opacity-100 group-hover:opacity-100"
        >
          {copied ? "copied" : "copy"}
        </button>
      </div>
      <pre
        className={`scroll-slim overflow-x-auto ${dense ? "p-2.5" : "p-3"} font-mono text-[11.5px] leading-relaxed text-ink-200`}
      >
        <code>
          {tokens.map((t, i) => (
            <span key={i} className={t.cls}>
              {t.text}
            </span>
          ))}
        </code>
      </pre>
    </div>
  );
}
