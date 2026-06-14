/**
 * Thin client for the Glowsky FastAPI backend.
 *
 * In dev the backend runs at http://localhost:8000 (`make run`). Override with
 * VITE_API_BASE. When the desktop shell bundles the backend as a Tauri sidecar, this
 * is the only place the base URL needs to change.
 */
const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "content-type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

// --- types (mirror the API response shapes) ----------------------------------

export interface Health {
  status: string;
  routes: Record<string, string>;
  tools: number;
  backends: { admet: string; docking: string };
}

export interface Candidate {
  smiles: string;
  inchikey: string;
  modification: string;
  properties: Record<string, number | boolean>;
  passed_filters: boolean;
  score: number;
}

export interface DesignPlan {
  max_analogs: number;
  constraints: Record<string, number | boolean | null>;
  rationale: string;
}

export interface TraceEntry {
  step: number;
  tool: string;
  tool_version: string;
  summary: string;
  duration_ms: number;
  cache_hit: boolean;
}

export interface DesignResult {
  run_id: string | null;
  goal: string;
  parent_smiles: string;
  plan: DesignPlan;
  candidates: Candidate[];
  trace: TraceEntry[];
  explanation: string;
  models_used: Record<string, string>;
}

// --- libraries & I/O ---------------------------------------------------------

export interface Project {
  id: string;
  org_id: string;
  name: string;
  description: string | null;
  target_profile: Record<string, unknown>;
  created_by: string | null;
}

export interface Library {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  kind: string;
  molecule_count: number;
}

export interface LibraryMolecule {
  id: string;
  name: string | null;
  canonical_smiles: string;
  inchikey: string;
  properties: Record<string, number | boolean | string>;
  source: string;
}

export interface LibraryDetail {
  library: Library;
  molecules: LibraryMolecule[];
}

export interface ImportResult {
  imported: number;
  duplicates: number;
  updated: number;
  invalid: { input: string; error: string }[];
  invalid_count: number;
}

export type IoFormat = "smiles" | "csv" | "sdf";

// --- tools -------------------------------------------------------------------

export interface JsonSchemaProp {
  type: string;
  items?: { type: string };
}

export interface ToolParameters {
  type: string;
  properties?: Record<string, JsonSchemaProp>;
  required?: string[];
}

export interface ToolSpec {
  name: string;
  version: string;
  category: string;
  description: string;
  parameters: ToolParameters;
  compute_class: string;
  latency_class: string;
  emits_structures: boolean;
}

export interface ToolProvenance {
  tool: string;
  version: string;
  compute_class: string;
  determinism: string;
  env_digest: string;
  input_hash: string;
  cache_hit: boolean;
  duration_ms: number;
  seed: number | null;
  error: string | null;
}

export interface ToolRunResult {
  output: unknown;
  provenance: ToolProvenance;
}

// --- settings (BYO-LLM) ------------------------------------------------------

export interface ProviderInfo {
  id: string;
  label: string;
  needs_base_url: boolean;
}

export interface Credential {
  id: string;
  provider: string;
  hint: string;
  base_url: string | null;
  label: string | null;
  status: string;
  created_at: string;
}

export interface RouteInfo {
  task_class: string;
  provider: string;
  model: string;
  source: "override" | "default";
}

// --- endpoints ---------------------------------------------------------------

export const api = {
  base: BASE,
  health: () => request<Health>("/health"),

  // projects
  listProjects: () => request<Project[]>("/projects"),
  createProject: (name: string) =>
    request<Project>("/projects", { method: "POST", body: JSON.stringify({ name }) }),

  // libraries
  listLibraries: (projectId: string) =>
    request<Library[]>(`/projects/${projectId}/libraries`),
  createLibrary: (projectId: string, name: string) =>
    request<Library>(`/projects/${projectId}/libraries`, {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  getLibrary: (libraryId: string) => request<LibraryDetail>(`/libraries/${libraryId}`),
  importMolecules: (libraryId: string, format: IoFormat, content: string) =>
    request<ImportResult>(`/libraries/${libraryId}/import`, {
      method: "POST",
      body: JSON.stringify({ format, content }),
    }),
  exportLibraryUrl: (libraryId: string, format: IoFormat) =>
    `${BASE}/libraries/${libraryId}/export?format=${format}`,

  // tools
  listTools: () => request<{ tools: ToolSpec[] }>("/tools").then((r) => r.tools),
  runTool: (name: string, args: Record<string, unknown>, seed?: number) =>
    request<ToolRunResult>(`/tools/${name}`, {
      method: "POST",
      body: JSON.stringify(seed === undefined ? { args } : { args, seed }),
    }),

  // settings — BYO-LLM credentials & routing
  listProviders: () =>
    request<{ providers: ProviderInfo[] }>("/settings/providers").then((r) => r.providers),
  listCredentials: () => request<Credential[]>("/settings/credentials"),
  addCredential: (provider: string, apiKey: string, baseUrl?: string) =>
    request<Credential>("/settings/credentials", {
      method: "POST",
      body: JSON.stringify({ provider, api_key: apiKey, base_url: baseUrl || null }),
    }),
  deleteCredential: (id: string) =>
    request<{ deleted: string }>(`/settings/credentials/${id}`, { method: "DELETE" }),
  getRoutes: () => request<RouteInfo[]>("/settings/routes"),
  setRoute: (taskClass: string, provider: string, model: string) =>
    request<RouteInfo>("/settings/routes", {
      method: "PUT",
      body: JSON.stringify({ task_class: taskClass, provider, model }),
    }),
  clearRoute: (taskClass: string) =>
    request<{ cleared: string }>(`/settings/routes/${taskClass}`, { method: "DELETE" }),
  design: (goal: string, seed_smiles: string) =>
    request<DesignResult>("/agent/design", {
      method: "POST",
      body: JSON.stringify({ goal, seed_smiles, persist: true }),
    }),
  profile: (smiles: string) =>
    request<{ canonical_smiles: string; inchikey: string; properties: Record<string, number | boolean> }>(
      "/molecules/profile",
      { method: "POST", body: JSON.stringify({ smiles }) },
    ),
  exportRunUrl: (runId: string, format: "ipynb" | "md") =>
    `${BASE}/runs/${runId}/export?format=${format}`,
};
