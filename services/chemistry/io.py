"""Molecule I/O: parse and serialize SMILES / CSV / SDF, and diff two molecules.

Every structure that enters through here passes the validation firewall
(validate_and_canonicalize) before it is trusted — imports are not exempt from the
anti-hallucination / anti-garbage guard (docs/12 #1). Parsers return a uniform
ParsedMolecule list with per-row validity so a partially-bad file degrades gracefully
instead of failing wholesale.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from rdkit import Chem

from services.chemistry.properties import compute_descriptors
from services.chemistry.validation import validate_and_canonicalize

SUPPORTED_FORMATS = ("smiles", "csv", "sdf")


@dataclass
class ParsedMolecule:
    valid: bool
    input: str
    canonical_smiles: str | None = None
    inchikey: str | None = None
    name: str | None = None
    properties: dict = field(default_factory=dict)
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "valid": self.valid, "input": self.input,
            "canonical_smiles": self.canonical_smiles, "inchikey": self.inchikey,
            "name": self.name, "properties": self.properties, "error": self.error,
        }


def _accept(raw: str, name: str | None, extra_props: dict | None = None) -> ParsedMolecule:
    """Run one structure through the firewall and shape it into a ParsedMolecule."""
    result = validate_and_canonicalize(raw)
    if not result.valid:
        return ParsedMolecule(valid=False, input=raw, name=name, error=result.error)
    return ParsedMolecule(
        valid=True, input=raw, canonical_smiles=result.canonical_smiles,
        inchikey=result.inchikey, name=name, properties=extra_props or {},
    )


# --- parsing ------------------------------------------------------------------


def parse_smiles(content: str) -> list[ParsedMolecule]:
    """One molecule per line: '<smiles>' or '<smiles> <name>' (whitespace-separated)."""
    out: list[ParsedMolecule] = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        smi = parts[0]
        name = parts[1].strip() if len(parts) > 1 else None
        out.append(_accept(smi, name))
    return out


def parse_csv(content: str, smiles_column: str = "smiles", name_column: str = "name") -> list[ParsedMolecule]:
    """Parse a CSV with a SMILES column; other columns are carried as properties.

    Column matching is case-insensitive. Non-SMILES/-name columns are attached to
    `properties` so imported data (e.g. assay values) isn't lost.
    """
    reader = csv.DictReader(io.StringIO(content))
    if reader.fieldnames is None:
        return []
    # Resolve the actual header names case-insensitively.
    lower = {f.lower(): f for f in reader.fieldnames}
    smi_field = lower.get(smiles_column.lower())
    name_field = lower.get(name_column.lower())
    if smi_field is None:
        raise ValueError(
            f"CSV has no '{smiles_column}' column (found: {reader.fieldnames})"
        )

    out: list[ParsedMolecule] = []
    for row in reader:
        smi = (row.get(smi_field) or "").strip()
        if not smi:
            continue
        name = (row.get(name_field) or "").strip() if name_field else None
        props = {k: v for k, v in row.items() if k not in {smi_field, name_field} and v not in (None, "")}
        out.append(_accept(smi, name or None, props))
    return out


def parse_sdf(content: str) -> list[ParsedMolecule]:
    """Parse an SDF/MOL block. SD tags become properties; canonicalized via the firewall."""
    out: list[ParsedMolecule] = []
    supplier = Chem.SDMolSupplier()
    supplier.SetData(content, sanitize=False, removeHs=False)
    for mol in supplier:
        if mol is None:
            out.append(ParsedMolecule(valid=False, input="<sdf record>",
                                      error="unparseable SDF record"))
            continue
        name = mol.GetProp("_Name") if mol.HasProp("_Name") else None
        props = {p: mol.GetProp(p) for p in mol.GetPropNames()}
        try:
            raw_smiles = Chem.MolToSmiles(mol)
        except Exception as exc:  # pre-sanitization can leave odd valences
            out.append(ParsedMolecule(valid=False, input=name or "<sdf record>",
                                      name=name, error=f"could not read structure: {exc}"))
            continue
        out.append(_accept(raw_smiles, name, props))
    return out


def parse(content: str, fmt: str, **kwargs) -> list[ParsedMolecule]:
    fmt = fmt.lower()
    if fmt == "smiles":
        return parse_smiles(content)
    if fmt == "csv":
        return parse_csv(content, **kwargs)
    if fmt == "sdf":
        return parse_sdf(content)
    raise ValueError(f"unsupported format {fmt!r}; expected one of {SUPPORTED_FORMATS}")


# --- serialization ------------------------------------------------------------


@dataclass
class ExportRow:
    canonical_smiles: str
    name: str | None = None
    properties: dict = field(default_factory=dict)


def to_smiles(rows: list[ExportRow]) -> str:
    lines = []
    for r in rows:
        lines.append(f"{r.canonical_smiles} {r.name}" if r.name else r.canonical_smiles)
    return "\n".join(lines) + ("\n" if lines else "")


def to_csv(rows: list[ExportRow]) -> str:
    # Stable column order: smiles, name, then the union of property keys (sorted).
    prop_keys = sorted({k for r in rows for k in r.properties})
    fieldnames = ["smiles", "name", *prop_keys]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for r in rows:
        record = {"smiles": r.canonical_smiles, "name": r.name or ""}
        record.update({k: r.properties.get(k, "") for k in prop_keys})
        writer.writerow(record)
    return buf.getvalue()


def to_sdf(rows: list[ExportRow]) -> str:
    buf = io.StringIO()
    writer = Chem.SDWriter(buf)
    try:
        for r in rows:
            mol = Chem.MolFromSmiles(r.canonical_smiles)
            if mol is None:
                continue
            if r.name:
                mol.SetProp("_Name", r.name)
            for k, v in r.properties.items():
                mol.SetProp(str(k), str(v))
            writer.write(mol)
    finally:
        writer.close()
    return buf.getvalue()


def serialize(rows: list[ExportRow], fmt: str) -> str:
    fmt = fmt.lower()
    if fmt == "smiles":
        return to_smiles(rows)
    if fmt == "csv":
        return to_csv(rows)
    if fmt == "sdf":
        return to_sdf(rows)
    raise ValueError(f"unsupported format {fmt!r}; expected one of {SUPPORTED_FORMATS}")


# --- diff ---------------------------------------------------------------------

_DIFF_KEYS = ("mw", "logp", "tpsa", "hbd", "hba", "rotatable_bonds", "qed")


def diff_molecules(smiles_a: str, smiles_b: str) -> dict:
    """Compare two molecules: identity + per-descriptor deltas (B − A)."""
    a = validate_and_canonicalize(smiles_a)
    b = validate_and_canonicalize(smiles_b)
    if not a.valid:
        raise ValueError(f"molecule A invalid: {a.error}")
    if not b.valid:
        raise ValueError(f"molecule B invalid: {b.error}")

    da = compute_descriptors(a.canonical_smiles)
    db = compute_descriptors(b.canonical_smiles)
    deltas = {k: round(db[k] - da[k], 3) for k in _DIFF_KEYS}
    return {
        "a": {"canonical_smiles": a.canonical_smiles, "inchikey": a.inchikey, "properties": da},
        "b": {"canonical_smiles": b.canonical_smiles, "inchikey": b.inchikey, "properties": db},
        "identical": a.inchikey == b.inchikey,
        "deltas": deltas,
    }
