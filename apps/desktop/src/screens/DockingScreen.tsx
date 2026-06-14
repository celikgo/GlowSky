import { useState } from "react";
import { api, ApiError, type DockResult, type DockingSample } from "../lib/api";
import { DockingPose3D } from "../components/DockingPose3D";

function parseVec(raw: string): number[] {
  return raw.split(/[\n,]+/).map((s) => s.trim()).filter(Boolean).map(Number);
}

export function DockingScreen() {
  // --- live docking form (adapter-gated; honest "not configured" by default) ---
  const [ligand, setLigand] = useState("CC(=O)Oc1ccccc1C(=O)O");
  const [receptor, setReceptor] = useState("/path/to/receptor.pdbqt");
  const [center, setCenter] = useState("0, 0, 0");
  const [size, setSize] = useState("20, 20, 20");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<DockResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notConfigured, setNotConfigured] = useState<string | null>(null);

  // --- sample pose viewer (real RCSB 1HSG complex) ---
  const [sample, setSample] = useState<DockingSample | null>(null);
  const [sampleLoading, setSampleLoading] = useState(false);
  const [sampleError, setSampleError] = useState<string | null>(null);

  async function runDock() {
    setRunning(true);
    setError(null);
    setNotConfigured(null);
    setResult(null);
    try {
      const res = await api.dock({
        ligand_smiles: ligand,
        receptor_ref: receptor,
        center: parseVec(center),
        size: parseVec(size),
      });
      setResult(res);
    } catch (e) {
      if (e instanceof ApiError && e.status === 501) setNotConfigured(e.message);
      else setError(e instanceof ApiError ? `${e.status}: ${e.message}` : "Could not reach the backend.");
    } finally {
      setRunning(false);
    }
  }

  async function loadSample() {
    setSampleLoading(true);
    setSampleError(null);
    try {
      setSample(await api.dockingSample());
    } catch {
      setSampleError("Could not load the sample complex.");
    } finally {
      setSampleLoading(false);
    }
  }

  return (
    <div className="docking">
      {/* Live docking */}
      <section className="docking__form card">
        <div className="section-title">Dock a ligand</div>
        <p className="docking__hint">
          Structure-based docking via the adapter-gated <span className="mono">dock</span> tool
          (AutoDock Vina / smina / gnina). Returns real pose geometry when an engine is configured —
          Glowsky never fabricates docking results.
        </p>
        <div className="formfield">
          <label className="field__label">ligand SMILES</label>
          <input className="input mono" value={ligand} onChange={(e) => setLigand(e.target.value)} />
        </div>
        <div className="formfield">
          <label className="field__label">receptor (.pdbqt path)</label>
          <input className="input mono" value={receptor} onChange={(e) => setReceptor(e.target.value)} />
        </div>
        <div className="docking__pocket">
          <div className="formfield">
            <label className="field__label">pocket center (x, y, z)</label>
            <input className="input mono" value={center} onChange={(e) => setCenter(e.target.value)} />
          </div>
          <div className="formfield">
            <label className="field__label">pocket size (x, y, z)</label>
            <input className="input mono" value={size} onChange={(e) => setSize(e.target.value)} />
          </div>
        </div>
        <button className="btn" onClick={runDock} disabled={running}>
          {running ? <span className="spinner" /> : "▶"}
          {running ? "Docking…" : "Run docking"}
        </button>

        {notConfigured ? (
          <div className="docking__notice">
            <strong>Docking engine not configured.</strong> {notConfigured}
          </div>
        ) : null}
        {error ? <div className="design__error">{error}</div> : null}

        {result ? (
          <>
            <div className="section-title">Poses</div>
            <div className="summary">
              <span className="chip chip--accent">{result.engine}</span>
              <span className="chip">
                best {result.score} {result.score_unit}
              </span>
              <span className="chip">{result.num_modes} modes</span>
            </div>
            <table className="docking__poses">
              <thead>
                <tr>
                  <th>mode</th>
                  <th>affinity ({result.score_unit})</th>
                  <th>rmsd l.b.</th>
                  <th>rmsd u.b.</th>
                  <th>geometry</th>
                </tr>
              </thead>
              <tbody>
                {result.poses.map((p) => (
                  <tr key={p.mode}>
                    <td>{p.mode}</td>
                    <td>{p.affinity}</td>
                    <td>{p.rmsd_lb}</td>
                    <td>{p.rmsd_ub}</td>
                    <td>{p.pdbqt ? "✓" : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : null}
      </section>

      {/* Sample pose viewer */}
      <section className="docking__sample card">
        <div className="section-title">Pose viewer</div>
        <p className="docking__hint">
          Receptor + ligand-pose overlay. Load a real protein–ligand complex to explore it in 3D.
        </p>
        {!sample ? (
          <button className="btn btn--ghost" onClick={loadSample} disabled={sampleLoading}>
            {sampleLoading ? <span className="spinner" /> : "⊕"}
            {sampleLoading ? "Loading…" : "Load sample complex (1HSG)"}
          </button>
        ) : (
          <>
            <div className="summary">
              <span className="chip chip--accent">{sample.name}</span>
            </div>
            <DockingPose3D receptorPdb={sample.receptor_pdb} ligand={sample.ligand_pdb} />
            <p className="docking__source">{sample.source}</p>
          </>
        )}
        {sampleError ? <div className="design__error">{sampleError}</div> : null}
      </section>
    </div>
  );
}
