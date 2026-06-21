/**
 * "Save selected analogs to a library" — the accept step that closes the design loop:
 * a chemist picks the analogs worth keeping and promotes them into a tenant-scoped library,
 * where they join the rest of the Library screen (grid, property columns, SMILES/CSV/SDF
 * export). Reuses the existing `/libraries/{id}/import` SMILES path — no new endpoint.
 */
import { useEffect, useState } from "react";
import { api, ApiError, type Candidate, type Library, type Project } from "../lib/api";

function errMsg(e: unknown): string {
  return e instanceof ApiError ? e.message : "Could not reach the backend. Is `make run` up?";
}

/** One SMILES per line; the modification rides along as the molecule name (rest-of-line). */
function toSmilesBlock(candidates: Candidate[]): string {
  return candidates
    .map((c) => {
      const name = (c.modification || "").replace(/\s+/g, " ").trim();
      return name ? `${c.smiles} ${name}` : c.smiles;
    })
    .join("\n");
}

export function SaveToLibraryModal({
  open,
  candidates,
  onClose,
  onSaved,
}: {
  open: boolean;
  candidates: Candidate[];
  onClose: () => void;
  onSaved: (libraryName: string, imported: number) => void;
}) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [libraries, setLibraries] = useState<Library[]>([]);
  const [libraryId, setLibraryId] = useState("");
  const [newLibName, setNewLibName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load projects when the modal opens.
  useEffect(() => {
    if (!open) return;
    setError(null);
    api
      .listProjects()
      .then((ps) => {
        setProjects(ps);
        setProjectId((cur) => cur || (ps[0]?.id ?? ""));
      })
      .catch((e) => setError(errMsg(e)));
  }, [open]);

  // Load libraries for the selected project.
  useEffect(() => {
    if (!open || !projectId) {
      setLibraries([]);
      setLibraryId("");
      return;
    }
    api
      .listLibraries(projectId)
      .then((libs) => {
        setLibraries(libs);
        setLibraryId(libs[0]?.id ?? "");
      })
      .catch((e) => setError(errMsg(e)));
  }, [open, projectId]);

  if (!open) return null;

  async function save() {
    if (!projectId) return;
    setBusy(true);
    setError(null);
    try {
      // Resolve the target library: an explicit new name wins, else the selected existing one.
      let targetId = libraryId;
      let targetName = libraries.find((l) => l.id === libraryId)?.name ?? "";
      if (newLibName.trim()) {
        const lib = await api.createLibrary(projectId, newLibName.trim());
        targetId = lib.id;
        targetName = lib.name;
      }
      if (!targetId) {
        setError("Pick a library or name a new one.");
        return;
      }
      const result = await api.importMolecules(targetId, "smiles", toSmilesBlock(candidates));
      onSaved(targetName, result.imported);
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  }

  const noProjects = projects.length === 0;

  return (
    <div className="editor-overlay" onClick={onClose}>
      <div className="save-modal" onClick={(e) => e.stopPropagation()}>
        <div className="editor-modal__head">
          <span className="editor-modal__title">
            Save {candidates.length} analog{candidates.length === 1 ? "" : "s"} to a library
          </span>
          <button className="editor-modal__close" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        <div className="save-modal__body">
          {noProjects ? (
            <div className="placeholder">
              <div className="placeholder__title">No projects yet</div>
              <div>Create a project in the Library tab first, then come back to save.</div>
            </div>
          ) : (
            <>
              <div className="field">
                <label className="field__label">Project</label>
                <select
                  className="input"
                  value={projectId}
                  onChange={(e) => setProjectId(e.target.value)}
                >
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="field">
                <label className="field__label">Existing library</label>
                <select
                  className="input"
                  value={libraryId}
                  onChange={(e) => setLibraryId(e.target.value)}
                  disabled={!!newLibName.trim() || libraries.length === 0}
                >
                  {libraries.length === 0 ? (
                    <option value="">No libraries in this project yet</option>
                  ) : (
                    libraries.map((l) => (
                      <option key={l.id} value={l.id}>
                        {l.name} · {l.molecule_count}
                      </option>
                    ))
                  )}
                </select>
              </div>

              <div className="field">
                <label className="field__label">…or new library</label>
                <input
                  className="input"
                  placeholder="e.g. Kinase analogs — round 1"
                  value={newLibName}
                  onChange={(e) => setNewLibName(e.target.value)}
                />
              </div>
            </>
          )}
        </div>

        <div className="editor-modal__actions">
          {error ? <span className="editor-modal__error">{error}</span> : null}
          <span className="library__spacer" />
          <button className="btn btn--ghost" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn"
            onClick={save}
            disabled={busy || noProjects || (!libraryId && !newLibName.trim())}
          >
            {busy ? <span className="spinner" /> : null}
            Save to library
          </button>
        </div>
      </div>
    </div>
  );
}
