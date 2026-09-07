// NEXT_PUBLIC_* is inlined at BUILD time, not read at runtime. Setting this in
// Vercel after a deploy does nothing until you redeploy — which is the single
// most common reason this app cannot reach its API.
const RAW_API_URL = process.env.NEXT_PUBLIC_API_URL?.trim();

/**
 * Repair the two mistakes people actually make when pasting a Railway domain.
 *
 * A value with no scheme is a *relative* URL, so the browser resolves it
 * against the Vercel origin and every call 404s against the wrong host. A
 * trailing `/api` double-counts the prefix this client already appends.
 */
function normalizeApiUrl(raw: string | undefined): { url: string; notes: string[] } {
  const notes: string[] = [];
  const trimmed = raw?.trim();
  if (!trimmed) return { url: "http://localhost:8000", notes };

  let url = trimmed;
  if (!/^https?:\/\//i.test(url)) {
    url = `https://${url}`;
    notes.push(
      `NEXT_PUBLIC_API_URL had no scheme, so it was read as a path relative to ` +
        `this site. Assuming https://. Set it to "${url}" to remove the guess.`,
    );
  }
  url = url.replace(/\/+$/, "");
  if (/\/api$/i.test(url)) {
    url = url.replace(/\/api$/i, "");
    notes.push(
      "NEXT_PUBLIC_API_URL ended in /api, which this client already appends. " +
        "Trailing /api removed — set it to the bare origin.",
    );
  }
  return { url, notes };
}

const NORMALIZED = normalizeApiUrl(RAW_API_URL);

export const API_URL = NORMALIZED.url;
export const API_URL_NOTES = NORMALIZED.notes;
export const API_URL_CONFIGURED = Boolean(RAW_API_URL);

/** Turn an opaque network or HTTP error into something actionable. */
export function diagnoseFetchFailure(error: unknown): string[] {
  const message = error instanceof Error ? error.message : String(error);
  const networkLevel = /failed to fetch|networkerror|load failed/i.test(message);
  const notFound = /\(404\)|^404\b/.test(message);
  const badGateway = /\(50[234]\)|^50[234]\b/.test(message);

  const hints: string[] = [...API_URL_NOTES];

  if (notFound) {
    hints.push(
      `A 404 means something answered, but it was not this API. Confirm ` +
        `${API_URL}/api/health returns JSON in a browser tab. If the URL above ` +
        `is missing https://, the browser treated it as a path on this site and ` +
        `asked Vercel for it instead of Railway.`,
    );
    return hints;
  }
  if (badGateway) {
    hints.push(
      `The API host answered but the service behind it did not. Check the ` +
        `Railway deploy logs — it may be restarting or out of memory.`,
    );
    return hints;
  }
  if (!networkLevel) return hints;

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
  cache_write_tokens: number;
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

// --- evaluation report ----------------------------------------------------
// Generated offline by `python -m app.evaluation.runner` and served static, so
// these types describe a file on disk rather than anything computed per request.

export interface EvalGrade {
  grade: number;
  name: string;
  meaning: string;
}

export interface EvalComponent {
  id: string;
  name: string;
  max: number;
  how: string;
  why: string;
}

export interface EvalRubric {
  k: number;
  noise_window: number;
  grades: EvalGrade[];
  components: EvalComponent[];
  empty_rule: string;
  rounding: string;
}

export interface EvalResult {
  rank: number;
  id: string;
  kind: string;
  title: string;
  snippet: string;
  score: number;
  why: string;
  grade: number;
  trap_reason: string;
  credited: string[];
}

export interface EvalStep {
  label: string;
  language: "sql" | "cypher" | "python" | "text" | "json";
  code: string;
  engine: string;
  row_count: number;
  latency_ms: number;
  note: string;
  error: string;
}

export interface EvalRun {
  mode: ModeId;
  score: number;
  components: {
    total: number;
    top_hit: number;
    coverage: number;
    cleanliness: number;
    retrieved: number;
    answers_found: number;
    answers_possible: number;
    traps_hit: number;
    irrelevant_in_window: number;
    first_answer_rank: number | null;
    empty: boolean;
  };
  verdict: string;
  commentary: string;
  results: EvalResult[];
  steps: EvalStep[];
  warnings: string[];
  latency_ms: number;
  fusion_legs: Record<string, number> | null;
}

export interface EvalTest {
  id: string;
  family: string;
  query: string;
  headline: string;
  preamble: string;
  what_good_looks_like: string;
  plan: {
    interpretation: string;
    keyword_query: string;
    semantic_query: string;
    cypher: string;
    sql_filter: string;
    ontology_terms: string[];
    plan_note?: string;
  };
  gold: Array<{ id: string; grade: number; grade_name: string; title: string }>;
  traps: Array<{ id: string; title: string; reason: string }>;
  runs: Record<ModeId, EvalRun>;
  best_mode: ModeId[];
  best_score: number;
  spread: number;
}

export interface EvalReport {
  schema_version: number;
  generated_at: string;
  environment: {
    python: string;
    embed_model: string;
    vector_engine: string;
    corpus: Record<string, number>;
  };
  planner: { source: string; note: string };
  rubric: EvalRubric;
  modes: Array<{ id: ModeId; label: string }>;
  families: Array<{ id: string; blurb: string }>;
  how_to_reproduce: string;
  caveats: string[];
  tests: EvalTest[];
  analysis: {
    leaderboard: Array<{
      mode: ModeId;
      label: string;
      mean: number;
      best: number;
      worst: number;
      wins: number;
      traps_retrieved: number;
      empty_answers: number;
      median_latency_ms: number;
    }>;
    by_family: Array<{
      family: string;
      blurb: string;
      tests: number;
      scores: Record<ModeId, number>;
    }>;
    findings: Array<{ title: string; body: string; evidence: string[] }>;
    totals: Record<string, number>;
  };
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
export const getEval = () => get<EvalReport>("/api/eval");
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
