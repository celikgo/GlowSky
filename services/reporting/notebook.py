"""Build a reproducible Jupyter notebook (.ipynb v4) from a persisted design run.

The notebook is self-contained, deterministic RDKit code: it embeds the parent and
candidate SMILES and *recomputes* their descriptors + filters locally, so a chemist
can re-run and verify the chemistry without the LLM or Glowsky in the loop. The agent's
plan, explanation, and tool trace are carried as Markdown for context/provenance.
"""
from __future__ import annotations

import json


def _md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}


def _code(text: str) -> dict:
    return {
        "cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
        "source": text.splitlines(keepends=True),
    }


def _candidate_rows(molecules: list[dict]) -> list[dict]:
    """Generated candidates only, as lightweight {smiles, name, properties} dicts."""
    return [
        {"smiles": m["canonical_smiles"], "name": m.get("name"),
         "properties": m.get("properties") or {}}
        for m in molecules if m.get("source") == "generated"
    ]


def build_notebook(run: dict, molecules: list[dict]) -> dict:
    """Assemble the .ipynb document (a plain dict ready to json.dump)."""
    parent = next(
        (m["canonical_smiles"] for m in molecules if m.get("source") == "user"), None
    )
    candidates = _candidate_rows(molecules)
    plan = run.get("plan") or {}
    constraints = plan.get("constraints") or {}
    models = run.get("models_used") or {}
    trace = run.get("trace") or []

    cells: list[dict] = []

    cells.append(_md(
        f"# Glowsky design run\n\n"
        f"**Goal:** {run.get('goal_text', '')}\n\n"
        f"- **Run ID:** `{run.get('id', 'n/a')}`\n"
        f"- **Created:** {run.get('created_at', 'n/a')}\n"
        f"- **Models:** {', '.join(f'{k}={v}' for k, v in models.items()) or 'offline mock'}\n"
        f"- **Plan rationale:** {plan.get('rationale', '') or 'n/a'}\n\n"
        f"This notebook reproduces the *deterministic chemistry* of the run with RDKit. "
        f"Structures were validated/canonicalized by Glowsky's firewall before storage."
    ))

    cells.append(_md("## 1. Setup"))
    cells.append(_code(
        "from rdkit import Chem\n"
        "from rdkit.Chem import Descriptors, Crippen, QED, rdMolDescriptors, Draw\n"
        "import pandas as pd\n"
    ))

    cells.append(_md("## 2. Parent and candidate structures"))
    # Embed as Python literals (repr), not JSON — these become executable code.
    cands_literal = repr([{"smiles": c["smiles"], "name": c["name"]} for c in candidates])
    cells.append(_code(
        f"parent_smiles = {parent!r}\n"
        f"candidates = {cands_literal}\n\n"
        "parent = Chem.MolFromSmiles(parent_smiles) if parent_smiles else None\n"
        "mols = [Chem.MolFromSmiles(c['smiles']) for c in candidates]\n"
        "print(f'parent: {parent_smiles}')\n"
        "print(f'{len(candidates)} candidate(s)')\n"
    ))

    cells.append(_md("## 3. Recompute descriptors (RDKit)"))
    cells.append(_code(
        "def descriptors(smiles):\n"
        "    m = Chem.MolFromSmiles(smiles)\n"
        "    return {\n"
        "        'smiles': smiles,\n"
        "        'mw': round(Descriptors.MolWt(m), 2),\n"
        "        'logp': round(Crippen.MolLogP(m), 2),\n"
        "        'tpsa': round(rdMolDescriptors.CalcTPSA(m), 2),\n"
        "        'hbd': rdMolDescriptors.CalcNumHBD(m),\n"
        "        'hba': rdMolDescriptors.CalcNumHBA(m),\n"
        "        'qed': round(QED.qed(m), 3),\n"
        "    }\n\n"
        "df = pd.DataFrame([descriptors(c['smiles']) for c in candidates])\n"
        "df\n"
    ))

    cells.append(_md("## 4. Apply the run's constraints"))
    cells.append(_code(
        f"constraints = {constraints!r}\n\n"
        "def passes(row):\n"
        "    if constraints.get('mw_max') is not None and row['mw'] > constraints['mw_max']:\n"
        "        return False\n"
        "    if constraints.get('logp_min') is not None and row['logp'] < constraints['logp_min']:\n"
        "        return False\n"
        "    if constraints.get('logp_max') is not None and row['logp'] > constraints['logp_max']:\n"
        "        return False\n"
        "    return True\n\n"
        "if not df.empty:\n"
        "    df['passes'] = df.apply(passes, axis=1)\n"
        "df\n"
    ))

    cells.append(_md("## 5. Visualize"))
    cells.append(_code(
        "valid = [m for m in mols if m is not None]\n"
        "legends = [c['name'] or c['smiles'] for c, m in zip(candidates, mols) if m is not None]\n"
        "Draw.MolsToGridImage(valid, legends=legends, molsPerRow=4, subImgSize=(220, 180)) "
        "if valid else 'no candidates'\n"
    ))

    if trace:
        trace_md = "## 6. Execution trace (provenance)\n\n| step | tool | summary | ms | cache |\n|---|---|---|---|---|\n"
        for t in trace:
            trace_md += (
                f"| {t.get('step', '')} | `{t.get('tool', '')}@{t.get('tool_version', '')}` "
                f"| {t.get('summary', '')} | {t.get('duration_ms', '')} "
                f"| {'hit' if t.get('cache_hit') else '—'} |\n"
            )
        cells.append(_md(trace_md))

    explanation = run.get("explanation")
    if explanation:
        cells.append(_md(f"## 7. Agent explanation\n\n{explanation}"))

    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
            "glowsky": {"run_id": run.get("id"), "exported_from": "glowsky"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def notebook_json(run: dict, molecules: list[dict]) -> str:
    return json.dumps(build_notebook(run, molecules), indent=1)
