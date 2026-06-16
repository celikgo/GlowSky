import { useEffect, useState } from "react";
import {
  api,
  ApiError,
  type IoFormat,
  type Library,
  type LibraryDetail,
  type Project,
} from "../lib/api";
import { LibraryMoleculeCard } from "./LibraryMoleculeCard";

const FORMATS: IoFormat[] = ["smiles", "csv", "sdf"];

const PLACEHOLDERS: Record<IoFormat, string> = {
  smiles: "c1ccccc1 benzene\nCCO ethanol\nCC(=O)Oc1ccccc1C(=O)O aspirin",
  csv: "smiles,name,IC50\nCCO,ethanol,12.5\nc1ccccc1,benzene,3.1",
  sdf: "(paste an SDF / MOL block)",
};

function errMsg(e: unknown): string {
  return e instanceof ApiError ? e.message : "Could not reach the backend. Is `make run` up?";
}

export function LibraryScreen() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [libraries, setLibraries] = useState<Library[]>([]);
  const [libraryId, setLibraryId] = useState("");
  const [detail, setDetail] = useState<LibraryDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Inline create + import form state
  const [newName, setNewName] = useState("");
  const [importFormat, setImportFormat] = useState<IoFormat>("smiles");
  const [importText, setImportText] = useState("");
  const [importing, setImporting] = useState(false);
  const [importMsg, setImportMsg] = useState<string | null>(null);

  // Load projects on mount.
  useEffect(() => {
    api
      .listProjects()
      .then((ps) => {
        setProjects(ps);
        if (ps.length) setProjectId((cur) => cur || ps[0].id);
      })
      .catch((e) => setError(errMsg(e)));
  }, []);

  // Load libraries when the project changes.
  useEffect(() => {
    if (!projectId) return;
    api
      .listLibraries(projectId)
      .then((libs) => {
        setLibraries(libs);
        setLibraryId(libs.length ? libs[0].id : "");
      })
      .catch((e) => setError(errMsg(e)));
  }, [projectId]);

  // Load the selected library's molecules.
  useEffect(() => {
    if (!libraryId) {
      setDetail(null);
      return;
    }
    api.getLibrary(libraryId).then(setDetail).catch((e) => setError(errMsg(e)));
  }, [libraryId]);

  async function refreshLibraries() {
    if (projectId) setLibraries(await api.listLibraries(projectId));
  }

  async function createProject() {
    if (!newName.trim()) return;
    try {
      const p = await api.createProject(newName.trim());
      setNewName("");
      setProjects((ps) => [p, ...ps]);
      setProjectId(p.id);
    } catch (e) {
      setError(errMsg(e));
    }
  }

  async function createLibrary() {
    if (!newName.trim() || !projectId) return;
    try {
      const lib = await api.createLibrary(projectId, newName.trim());
      setNewName("");
      await refreshLibraries();
      setLibraryId(lib.id);
    } catch (e) {
      setError(errMsg(e));
    }
  }

  async function runImport() {
    if (!libraryId || !importText.trim()) return;
    setImporting(true);
    setImportMsg(null);
    try {
      const r = await api.importMolecules(libraryId, importFormat, importText);
      const bits = [`${r.imported} imported`];
      if (r.updated) bits.push(`${r.updated} updated`);
      if (r.duplicates) bits.push(`${r.duplicates} duplicate`);
      if (r.invalid_count) bits.push(`${r.invalid_count} invalid`);
      setImportMsg(bits.join(" · "));
      setImportText("");
      setDetail(await api.getLibrary(libraryId));
      await refreshLibraries();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setImporting(false);
    }
  }

  const noProjects = projects.length === 0;

  return (
    <div className="library">
      {/* Project + library selectors */}
      <section className="library__bar card">
        <div className="library__selectors">
          <label className="field__label">Project</label>
          <select
            className="input library__select"
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
            disabled={noProjects}
          >
            {noProjects ? <option value="">No projects yet</option> : null}
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
        <div className="library__newrow">
          <input
            className="input"
            placeholder={noProjects ? "Name your first project…" : "New project or library name…"}
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
          />
          <button className="btn btn--ghost" onClick={createProject} disabled={!newName.trim()}>
            + Project
          </button>
          <button
            className="btn btn--ghost"
            onClick={createLibrary}
            disabled={!newName.trim() || !projectId}
          >
            + Library
          </button>
        </div>
      </section>

      {error ? <div className="design__error">{error}</div> : null}

      {/* Library tabs */}
      {libraries.length ? (
        <div className="library__tabs">
          {libraries.map((lib) => (
            <button
              key={lib.id}
              className={`library__tab ${lib.id === libraryId ? "library__tab--active" : ""}`}
              onClick={() => setLibraryId(lib.id)}
            >
              {lib.name}
              <span className="library__count">{lib.molecule_count}</span>
            </button>
          ))}
        </div>
      ) : projectId ? (
        <div className="placeholder">
          <div className="placeholder__title">No libraries yet</div>
          <div>Create one above, then import molecules.</div>
        </div>
      ) : null}

      {/* Selected library: import + export + molecules */}
      {libraryId && detail ? (
        <>
          <section className="library__import card">
            <div className="library__importhead">
              <div className="field__label">Import molecules</div>
              <div className="library__formats">
                {FORMATS.map((f) => (
                  <button
                    key={f}
                    className={`chip ${importFormat === f ? "chip--accent" : ""}`}
                    onClick={() => setImportFormat(f)}
                  >
                    {f.toUpperCase()}
                  </button>
                ))}
              </div>
            </div>
            <textarea
              className="textarea mono"
              value={importText}
              onChange={(e) => setImportText(e.target.value)}
              placeholder={PLACEHOLDERS[importFormat]}
            />
            <div className="library__importactions">
              <button className="btn" onClick={runImport} disabled={importing || !importText.trim()}>
                {importing ? <span className="spinner" /> : null}
                {importing ? "Importing…" : "Import"}
              </button>
              {importMsg ? <span className="chip chip--success">{importMsg}</span> : null}
              <span className="library__spacer" />
              <span className="field__label">Export</span>
              {FORMATS.map((f) => (
                <button
                  key={f}
                  className="chip chip--btn"
                  onClick={() => api.downloadLibrary(libraryId, f).catch((e) => setError(errMsg(e)))}
                >
                  ⬇ {f}
                </button>
              ))}
            </div>
          </section>

          <div className="section-title">
            {detail.library.name} · {detail.molecules.length} molecules
          </div>
          {detail.molecules.length ? (
            <div className="grid">
              {detail.molecules.map((m) => (
                <LibraryMoleculeCard key={m.id} mol={m} />
              ))}
            </div>
          ) : (
            <div className="placeholder">
              <div>This library is empty — import some molecules above.</div>
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}
