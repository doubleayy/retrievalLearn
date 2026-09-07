// NEXT_PUBLIC_* is inlined at BUILD time, not read at runtime. Setting this in
// Vercel after a deploy does nothing until you redeploy — which is the single
// most common reason this app cannot reach its API.
const RAW_API_URL = process.env.NEXT_PUBLIC_API_URL?.trim();

export const API_URL = (RAW_API_URL || "http://localhost:8000").replace(/\/$/, "");
export const API_URL_CONFIGURED = Boolean(RAW_API_URL);

/** Turn an opaque `TypeError: Failed to fetch` into something actionable. */
export function diagnoseFetchFailure(error: unknown): string[] {
  const message = error instanceof Error ? error.message : String(error);
  const networkLevel = /failed to fetch|networkerror|load failed/i.test(message);
  if (!networkLevel) return [];

  const hints: string[] = [];
  const pageIsHttps =
    typeof window !== "undefined" && window.location.protocol === "https:";

  if (!API_URL_CONFIGURED) {
    hints.push(
      "NEXT_PUBLIC_API_URL was not set when this site was built, so it is " +
        "falling back to http://localhost:8000 — which points at your own " +
        "machine, not the API. Set it in Vercel, then redeploy: the value is " +
        "baked in at build time, so saving it alone changes nothing.",
    );
  }
  if (pageIsHttps && API_URL.startsWith("http://")) {
    hints.push(
      `This page is served over HTTPS but the API URL is ${API_URL}. Browsers ` +
        "block insecure requests from a secure page. Use the https:// form.",
    );
  }
  if (API_URL_CONFIGURED) {
    hints.push(
      "If the URL above is correct, this is almost certainly CORS: set " +
        "CORS_ORIGINS on the API to this site's exact origin " +
        `(${typeof window !== "undefined" ? window.location.origin : "your Vercel URL"}) ` +
        "and restart it. Your browser console will name the blocked origin.",
    );
    hints.push(
      `Check the API is up directly: open ${API_URL}/api/health in a new tab.`,
    );
  }
  return hints;
}

export type ModeId =
  | "keyword"
  | "semantic"
  | "graph"
  | "hybrid"
  | "hybrid_ontology";

export interface ExecutedStep {
  label: string;
  language: "sql" | "cypher" | "python" | "text" | "json";
  code: string;
  params: Record<string, unknown>;
  engine: string;
  row_count: number;
  latency_ms: number;
  note: string;
  error: string;
  table?: { columns: string[]; rows: unknown[][] } | null;
}

export interface ResultItem {
  id: string;
  kind: "article" | "player" | "trade" | "path";
  title: string;
  snippet: string;
  score: number;
  rank: number;
  score_breakdown: Record<string, any>;
  why: string;
  data: Record<string, any>;
}

export interface OntologyTrace {
  matched_phrases: Array<{
    phrase: string;
    resolved_to: string;
    kind: "class" | "property";
    label: string;
    defined?: boolean;
    equivalent_to?: string;
    graph_rel?: string;
    derived?: boolean;
  }>;
  expanded_classes: string[];
  expanded_synonyms: string[];
  sql_predicates: string[];
  derived_relations: string[];
  turtle: string;
}

export interface PlanInfo {
  model: string;
  interpretation: string;
  explanation: string;
  entities: Array<{ text: string; kind: string; resolved_id: string }>;
  keyword_query: string;
  semantic_query: string;
  cypher: string;
  sql_filter: string;
  ontology_terms: string[];
  latency_ms: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cached: boolean;
  repaired: boolean;
}

export interface SearchResponse {
  query: string;
  mode: ModeId;
  plan: PlanInfo;
  steps: ExecutedStep[];
  results: ResultItem[];
  ontology_trace: OntologyTrace | null;
  fusion: {
    method: string;
    k: number;
    weights?: Record<string, number>;
    formula: string;
    why: string;
    legs: Record<string, number>;
    detail: Record<string, { total: number; sources: Record<string, any> }>;
  } | null;
  explain: { what_happened: string; strengths: string[]; limits: string[] };
  timings: Record<string, number>;
  warnings: string[];
}

export interface ModeInfo {
  id: ModeId;
  name: string;
  tagline: string;
  language: string;
  one_liner: string;
}

export interface ExampleQuery {
  id: string;
  query: string;
  headline: string;
  lesson: string;
  try_modes: ModeId[];
}

export interface Dataset {
  id: string;
  name: string;
  shape: string;
  table: string;
  grain: string;
  description: string;
  columns: string[][];
  visible_to: ModeId[];
  note: string;
  row_count: number;
  sample: Record<string, unknown>[];
}

export interface CatalogResponse {
  datasets: Dataset[];
  totals: Record<string, number>;
  graph: Record<string, number>;
  vector_engine: string;
  build_ms: Record<string, number>;
  disclaimer: string;
}

export interface OntologyResponse {
  iri: string;
  prefix: string;
  description: string;
  classes: Array<Record<string, any>>;
  properties: Array<Record<string, any>>;
  rules: Array<{ id: string; head: string; body: string; description: string }>;
  showcase: Array<{ phrase: string; expands_to: string[]; becomes: string }>;
  turtle: string;
  defined_class_members: Record<string, string[]>;
  conflict_kinds: string[];
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const getModes = () => get<{ modes: ModeInfo[] }>("/api/modes");
export const getExamples = () => get<{ examples: ExampleQuery[] }>("/api/examples");
export const getCatalog = () => get<CatalogResponse>("/api/catalog");
export const getOntology = () => get<OntologyResponse>("/api/ontology");
export const getHealth = () =>
  get<{ ok: boolean; planner_model: string; planner_configured: boolean; build: any }>(
    "/api/health",
  );

export async function search(
  query: string,
  mode: ModeId,
  limit = 8,
): Promise<SearchResponse> {
  const res = await fetch(`${API_URL}/api/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, mode, limit }),
  });
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* keep the status-code message */
    }
    throw new Error(detail);
  }
  return res.json();
}

export const MODE_ACCENT: Record<ModeId, string> = {
  keyword: "#f5a524",
  semantic: "#22b8cf",
  graph: "#a78bfa",
  hybrid: "#4ade80",
  hybrid_ontology: "#f472b6",
};

export const MODE_ORDER: ModeId[] = [
  "keyword",
  "semantic",
  "graph",
  "hybrid",
  "hybrid_ontology",
];
