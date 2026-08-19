import { useEffect, useMemo, useState } from "react";
import {
  api,
  ApiError,
  type JsonSchemaProp,
  type ToolRunResult,
  type ToolSpec,
} from "../lib/api";
import { MoleculeStructure } from "../components/MoleculeStructure";

// Prefill the first plausible field so most tools are one-click runnable.
function prefill(name: string, prop: JsonSchemaProp): string {
  const n = name.toLowerCase();
  if (prop.type === "array") {
    if (n.includes("smiles")) return "CCO\nc1ccccc1\nCC(=O)Oc1ccccc1C(=O)O";
    if (n.includes("center")) return "0, 0, 0";
    if (n.includes("size")) return "20, 20, 20";
    if (n.includes("endpoint")) return "solubility\nherg";
    return "";
  }
  if (n.includes("smarts")) return "c1ccccc1";
  if (n.includes("smiles")) return "c1ccccc1C(=O)O";
  if (prop.type === "integer" || prop.type === "number") return n.includes("max") ? "8" : "";
  return "";
}

// Turn a raw form value into the JSON type the tool expects.
function coerce(prop: JsonSchemaProp, raw: string): unknown {
  if (prop.type === "integer") return raw === "" ? undefined : parseInt(raw, 10);
  if (prop.type === "number") return raw === "" ? undefined : parseFloat(raw);
  if (prop.type === "boolean") return raw === "true";
  if (prop.type === "array") {
    const items = raw.split(/[\n,]+/).map((s) => s.trim()).filter(Boolean);
    return prop.items?.type === "number" ? items.map(Number) : items;
  }
  return raw;
}

// Pull any SMILES out of a result so we can draw the structures involved.
function collectSmiles(output: unknown): string[] {
  const out: string[] = [];
  const take = (o: unknown) => {
    if (o && typeof o === "object") {
      const rec = o as Record<string, unknown>;
      const s = rec.canonical_smiles ?? rec.smiles;
      if (typeof s === "string") out.push(s);
    }
  };
  if (Array.isArray(output)) output.forEach(take);
  else take(output);
  return out.slice(0, 8);
}

export function ToolsScreen() {
  const [tools, setTools] = useState<ToolSpec[]>([]);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<ToolSpec | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});
  const [seed, setSeed] = useState("");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<ToolRunResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listTools()
      .then((ts) => {
        setTools(ts);
        if (ts.length) select(ts[0]);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Backend offline. Is `make run` up?"));
  }, []);

  function select(tool: ToolSpec) {
    setSelected(tool);
    setResult(null);
    setError(null);
    const props = tool.parameters.properties ?? {};
    setForm(Object.fromEntries(Object.entries(props).map(([k, p]) => [k, prefill(k, p)])));
  }

  const grouped = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = tools.filter(
      (t) => !q || t.name.toLowerCase().includes(q) || t.description.toLowerCase().includes(q),
    );
    const by: Record<string, ToolSpec[]> = {};
    for (const t of filtered) (by[t.category] ??= []).push(t);
    return Object.entries(by).sort(([a], [b]) => a.localeCompare(b));
  }, [tools, query]);

  async function run() {
    if (!selected) return;
    setRunning(true);
    setError(null);
    setResult(null);
    const props = selected.parameters.properties ?? {};
    const required = selected.parameters.required ?? [];
    const args: Record<string, unknown> = {};
    for (const [k, p] of Object.entries(props)) {
      const v = coerce(p, form[k] ?? "");
      if (v !== undefined && v !== "" && !(Array.isArray(v) && v.length === 0)) args[k] = v;
      else if (required.includes(k)) args[k] = v; // let the backend report the validation error
    }
    try {
      const seedNum = seed.trim() === "" ? undefined : parseInt(seed, 10);
      setResult(await api.runTool(selected.name, args, seedNum));
    } catch (e) {
      setError(e instanceof ApiError ? `${e.status}: ${e.message}` : "Could not reach the backend.");
    } finally {
      setRunning(false);
    }
  }

  const smiles = result ? collectSmiles(result.output) : [];

  return (
    <div className="tools">
      {/* Registry list */}
      <aside className="tools__list">
        <input
          className="input tools__search"
          placeholder="Search tools…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        {grouped.map(([category, items]) => (
          <div key={category} className="tools__group">
            <div className="tools__category">{category}</div>
            {items.map((t) => (
              <button
                key={t.name}
                className={`toolitem ${selected?.name === t.name ? "toolitem--active" : ""}`}
                onClick={() => select(t)}
              >
                <span className="toolitem__name mono">{t.name}</span>
                <span className="toolitem__desc">{t.description}</span>
              </button>
            ))}
          </div>
        ))}
      </aside>

      {/* Detail + run */}
      <div className="tools__detail">
        {selected ? (
          <>
            <div className="tools__head">
              <h2 className="tools__title mono">{selected.name}</h2>
              <div className="summary">
                <span className="chip chip--accent">{selected.category}</span>
                <span className="chip">v{selected.version}</span>
                <span className="chip">{selected.compute_class}</span>
                <span className="chip">{selected.latency_class}</span>
                {selected.emits_structures ? <span className="chip">emits structures</span> : null}
              </div>
              <p className="tools__desc">{selected.description}</p>
            </div>

            <section className="tools__form card">
              {Object.entries(selected.parameters.properties ?? {}).map(([name, prop]) => {
                const req = (selected.parameters.required ?? []).includes(name);
                const isArray = prop.type === "array";
                return (
                  <div className="formfield" key={name}>
                    <label className="field__label">
                      {name}
                      <span className="formfield__type">
                        {prop.type}
                        {prop.items ? `<${prop.items.type}>` : ""}
                        {req ? " · required" : ""}
                      </span>
                    </label>
                    {isArray ? (
                      <textarea
                        className="textarea mono"
                        value={form[name] ?? ""}
                        onChange={(e) => setForm((f) => ({ ...f, [name]: e.target.value }))}
                        placeholder={prop.items?.type === "number" ? "comma-separated" : "one per line"}
                      />
                    ) : (
                      <input
                        className="input mono"
                        type={prop.type === "integer" || prop.type === "number" ? "number" : "text"}
                        value={form[name] ?? ""}
                        onChange={(e) => setForm((f) => ({ ...f, [name]: e.target.value }))}
                      />
                    )}
                  </div>
                );
              })}
              <div className="tools__runrow">
                <button className="btn" onClick={run} disabled={running}>
                  {running ? <span className="spinner" /> : "▶"}
                  {running ? "Running…" : "Run tool"}
                </button>
                <div className="formfield formfield--seed">
                  <input
                    className="input mono"
                    placeholder="seed (optional)"
                    value={seed}
                    onChange={(e) => setSeed(e.target.value)}
                  />
                </div>
              </div>
            </section>

            {error ? <div className="design__error">{error}</div> : null}

            {result ? (
              <>
                <div className="section-title">Result</div>
                <div className="summary">
                  <span className="chip">{result.provenance.duration_ms} ms</span>
                  <span className={`chip ${result.provenance.cache_hit ? "chip--success" : ""}`}>
                    {result.provenance.cache_hit ? "cache hit" : "computed"}
                  </span>
                  <span className="chip">{result.provenance.determinism}</span>
                  {result.provenance.seed !== null ? (
                    <span className="chip">seed {result.provenance.seed}</span>
                  ) : null}
                </div>

                {smiles.length ? (
                  <div className="tools__structures">
                    {smiles.map((s, i) => (
                      <div className="tools__struct" key={`${s}-${i}`}>
                        <MoleculeStructure smiles={s} width={180} height={130} />
                      </div>
                    ))}
                  </div>
                ) : null}

                <pre className="tools__output mono">{JSON.stringify(result.output, null, 2)}</pre>
              </>
            ) : null}
          </>
        ) : error ? (
          <div className="design__error">{error}</div>
        ) : (
          <div className="placeholder">
            <div>Loading the tool registry…</div>
          </div>
        )}
      </div>
    </div>
  );
}
