/**
 * `@`-context picker for the Composer: attach molecules from a library (or paste a SMILES) to a
 * chat turn. The first attached molecule also seeds a design request when no seed is set yet, so
 * "@aspirin → make 10 analogs" works without a separate seed step.
 */
import { useEffect, useState } from "react"
import {
  api,
  ApiError,
  type ChatContextMolecule,
  type Library,
  type LibraryDetail,
  type Project,
} from "../lib/api"

function errMsg(e: unknown): string {
  return e instanceof ApiError ? e.message : "Could not reach the backend. Is `make run` up?"
}

export function ContextPickerModal({
  open,
  onClose,
  onAttach,
}: {
  open: boolean
  onClose: () => void
  onAttach: (molecules: ChatContextMolecule[]) => void
}) {
  const [projects, setProjects] = useState<Project[]>([])
  const [projectId, setProjectId] = useState("")
  const [libraries, setLibraries] = useState<Library[]>([])
  const [libraryId, setLibraryId] = useState("")
  const [detail, setDetail] = useState<LibraryDetail | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [paste, setPaste] = useState("")
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setError(null)
    setSelected(new Set())
    api
      .listProjects()
      .then((ps) => {
        setProjects(ps)
        setProjectId((cur) => cur || (ps[0]?.id ?? ""))
      })
      .catch((e) => setError(errMsg(e)))
  }, [open])

  useEffect(() => {
    if (!open || !projectId) return
    api
      .listLibraries(projectId)
      .then((libs) => {
        setLibraries(libs)
        setLibraryId(libs[0]?.id ?? "")
      })
      .catch((e) => setError(errMsg(e)))
  }, [open, projectId])

  useEffect(() => {
    if (!libraryId) {
      setDetail(null)
      return
    }
    api.getLibrary(libraryId).then(setDetail).catch((e) => setError(errMsg(e)))
  }, [libraryId])

  if (!open) return null

  function toggle(id: string) {
    setSelected((cur) => {
      const next = new Set(cur)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function attach() {
    const mols: ChatContextMolecule[] = []
    if (detail) {
      for (const m of detail.molecules) {
        if (selected.has(m.id)) mols.push({ smiles: m.canonical_smiles, name: m.name })
      }
    }
    const pasted = paste.trim()
    if (pasted) mols.push({ smiles: pasted, name: null })
    if (mols.length) onAttach(mols)
  }

  const total = selected.size + (paste.trim() ? 1 : 0)

  return (
    <div className="editor-overlay" onClick={onClose}>
      <div className="save-modal" onClick={(e) => e.stopPropagation()}>
        <div className="editor-modal__head">
          <span className="editor-modal__title">Attach context molecules</span>
          <button className="editor-modal__close" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        <div className="save-modal__body">
          {projects.length === 0 ? (
            <div className="placeholder">
              <div>No libraries yet — paste a SMILES below, or build a library first.</div>
            </div>
          ) : (
            <>
              <div className="composer__pickrow">
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
                <select
                  className="input"
                  value={libraryId}
                  onChange={(e) => setLibraryId(e.target.value)}
                  disabled={libraries.length === 0}
                >
                  {libraries.length === 0 ? (
                    <option value="">No libraries</option>
                  ) : (
                    libraries.map((l) => (
                      <option key={l.id} value={l.id}>
                        {l.name} · {l.molecule_count}
                      </option>
                    ))
                  )}
                </select>
              </div>

              <div className="composer__pickerlist">
                {detail && detail.molecules.length ? (
                  detail.molecules.map((m) => (
                    <label key={m.id} className="composer__pickitem">
                      <input
                        type="checkbox"
                        checked={selected.has(m.id)}
                        onChange={() => toggle(m.id)}
                      />
                      <span className="composer__pickname">{m.name || "molecule"}</span>
                      <span className="mono composer__picksmiles">{m.canonical_smiles}</span>
                    </label>
                  ))
                ) : (
                  <div className="placeholder">This library is empty.</div>
                )}
              </div>
            </>
          )}

          <div className="field">
            <label className="field__label">…or paste a SMILES</label>
            <input
              className="input mono"
              placeholder="e.g. CC(=O)Oc1ccccc1C(=O)O"
              value={paste}
              onChange={(e) => setPaste(e.target.value)}
            />
          </div>
        </div>

        <div className="editor-modal__actions">
          {error ? <span className="editor-modal__error">{error}</span> : null}
          <span className="library__spacer" />
          <button className="btn btn--ghost" onClick={onClose}>
            Cancel
          </button>
          <button className="btn" onClick={attach} disabled={total === 0}>
            Attach {total || ""}
          </button>
        </div>
      </div>
    </div>
  )
}
