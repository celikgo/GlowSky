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

// --- auth: nakitte-carbon-auth access token (the only credential) -------------
// Every backend call carries a platform JWT. The desktop has no login flow yet, so
// the token is pasted in Settings and persisted locally; an env default (VITE_AUTH_TOKEN)
// is a convenience for dev. Sent as `Authorization: Bearer` on HTTP and `?token=`/init
// frame on WebSockets (a WS handshake can't carry a header).
const TOKEN_KEY = "glowsky_token";

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) ?? (import.meta.env.VITE_AUTH_TOKEN as string | undefined) ?? "";
}

export function setToken(token: string): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

function authHeaders(): Record<string, string> {
  const t = getToken();
  return t ? { authorization: `Bearer ${t}` } : {};
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      ...authHeaders(),
      ...((init?.headers as Record<string, string>) ?? {}),
    },
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

export interface Conformer {
  canonical_smiles: string;
  inchikey: string;
  molblock: string;
  energy_kcal_mol: number | null;
  seed: number;
}

export interface DockingSample {
  id: string;
  name: string;
  source: string;
  receptor_pdb: string;
  ligand_pdb: string;
}

export interface DockPose {
  mode: number;
  affinity: number;
  rmsd_lb: number;
  rmsd_ub: number;
  pdbqt: string | null;
}

export interface DockResult {
  engine: string;
  score: number;
  score_unit: string;
  num_modes: number;
  poses: DockPose[];
  best_pose_pdbqt: string | null;
  pocket: { center: number[]; size: number[] };
}

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

// --- design streaming (WebSocket) --------------------------------------------

/** Live milestones from the agentic design loop, in the order the server emits them. */
export interface DesignStreamHandlers {
  onPlan?: (parentSmiles: string, plan: DesignPlan) => void;
  onCandidate?: (candidate: Candidate) => void;
  onTrace?: (entry: TraceEntry) => void;
  onRanked?: (order: string[]) => void;
  onExplanation?: (text: string) => void;
  onComplete?: (result: DesignResult) => void;
  onError?: (message: string) => void;
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

  /**
   * Run the design loop over a WebSocket, invoking `h` as each milestone streams in
   * (plan → candidate… → ranked → explanation → complete). Returns a cancel function
   * that closes the socket. The token rides the init frame (a WS can't send a header).
   */
  streamDesign(goal: string, seed_smiles: string, h: DesignStreamHandlers): () => void {
    const url = `${BASE.replace(/^http/i, "ws")}/agent/design/stream`;
    let ws: WebSocket;
    try {
      ws = new WebSocket(url);
    } catch {
      h.onError?.("Could not open a connection to the backend. Is `make run` up?");
      return () => {};
    }
    ws.onopen = () =>
      ws.send(JSON.stringify({ goal, seed_smiles, persist: true, token: getToken() }));
    ws.onmessage = (ev) => {
      let m: { type: string; [k: string]: unknown };
      try {
        m = JSON.parse(ev.data as string);
      } catch {
        return;
      }
      switch (m.type) {
        case "plan":
          h.onPlan?.(m.parent_smiles as string, m.plan as DesignPlan);
          break;
        case "candidate":
          h.onCandidate?.(m.candidate as Candidate);
          break;
        case "trace":
          h.onTrace?.(m.record as TraceEntry);
          break;
        case "ranked":
          h.onRanked?.(m.order as string[]);
          break;
        case "explanation":
          h.onExplanation?.(m.text as string);
          break;
        case "complete":
          h.onComplete?.(m.result as DesignResult);
          break;
        case "error":
          h.onError?.(m.error as string);
          break;
      }
    };
    ws.onerror = () => h.onError?.("Could not reach the backend. Is `make run` up?");
    return () => {
      try {
        ws.close();
      } catch {
        /* already closing */
      }
    };
  },
  profile: (smiles: string) =>
    request<{ canonical_smiles: string; inchikey: string; properties: Record<string, number | boolean> }>(
      "/molecules/profile",
      { method: "POST", body: JSON.stringify({ smiles }) },
    ),
  conformer: (smiles: string) =>
    request<Conformer>("/molecules/conformer", {
      method: "POST",
      body: JSON.stringify({ smiles }),
    }),
  dockingSample: () => request<DockingSample>("/examples/docking/sample"),
  dock: (args: {
    ligand_smiles: string;
    receptor_ref: string;
    center: number[];
    size: number[];
  }) =>
    request<{ output: DockResult }>("/tools/dock", {
      method: "POST",
      body: JSON.stringify({ args }),
    }).then((r) => r.output),
  exportRunUrl: (runId: string, format: "ipynb" | "md") =>
    `${BASE}/runs/${runId}/export?format=${format}`,
};
