"""Container-tool manifests (docs/13 §6).

A researcher describes their tool in a `glowsky-tool.yaml`, points it at a Docker
image that speaks the tool ABI (see runtimes/container.py), and Glowsky registers it
as a first-class, agent-callable ToolSpec — no Glowsky code changes. The same
contract (cache, firewall, provenance, routing) applies as for built-in tools.
"""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from services.tools.registry import ToolRegistry
from services.tools.runtimes.container import ContainerRuntime
from services.tools.spec import (
    ComputeClass,
    Determinism,
    Egress,
    LatencyClass,
    Resources,
    Runtime,
    ToolCategory,
    ToolSpec,
)

MANIFEST_GLOB = "**/glowsky-tool.yaml"


class ManifestResources(BaseModel):
    cpu: float = 1.0
    mem_mb: int = 1024
    gpu: int = 0
    timeout_s: int = 120


class ContainerToolManifest(BaseModel):
    """Parsed glowsky-tool.yaml. `image` must be resolvable by the Docker daemon."""

    name: str
    version: str = "0.1.0"
    category: ToolCategory = ToolCategory.PROPERTY
    summary: str = ""
    image: str
    input_schema: dict = Field(default_factory=dict)
    output_schema: dict = Field(default_factory=dict)
    compute_class: ComputeClass = ComputeClass.CPU_HEAVY
    latency_class: LatencyClass = LatencyClass.SHORT
    determinism: Determinism = Determinism.DETERMINISTIC
    emits_structures: bool = False
    egress: Egress = Egress.NONE
    resources: ManifestResources = Field(default_factory=ManifestResources)
    user: str | None = "65534:65534"

    @property
    def env_digest(self) -> str:
        # The image ref pins the environment for reproducibility (use a @sha256 digest
        # in production rather than a mutable tag).
        return self.image


def spec_from_manifest(m: ContainerToolManifest, runtime: ContainerRuntime) -> ToolSpec:
    res = Resources(
        cpu=m.resources.cpu, mem_mb=m.resources.mem_mb,
        gpu=m.resources.gpu, timeout_s=m.resources.timeout_s,
    )

    def handler(**args):
        # Executor may inject `seed` for SEEDED tools — pass it through in the ABI args.
        return runtime.run(
            image=m.image, args=args, resources=res, egress=m.egress, user=m.user
        )

    return ToolSpec(
        name=m.name, version=m.version, category=m.category, summary=m.summary,
        handler=handler, input_schema=m.input_schema, output_schema=m.output_schema,
        compute_class=m.compute_class, latency_class=m.latency_class,
        determinism=m.determinism, emits_structures=m.emits_structures,
        resources=res, runtime=Runtime.CONTAINER, env_digest=m.env_digest, egress=m.egress,
    )


def load_manifest_file(path: str | Path) -> ContainerToolManifest:
    data = yaml.safe_load(Path(path).read_text())
    return ContainerToolManifest(**data)


def load_container_tools(
    registry: ToolRegistry, tools_dir: str | Path, runtime: ContainerRuntime | None = None
) -> list[str]:
    """Discover and register every container tool under tools_dir. Returns names loaded.

    Safe to call when the dir is missing or Docker is unavailable — it simply loads
    what it can and skips the rest (registration does not require a running daemon;
    only execution does)."""
    directory = Path(tools_dir)
    if not directory.exists():
        return []
    runtime = runtime or ContainerRuntime()
    loaded: list[str] = []
    for manifest_path in sorted(directory.glob(MANIFEST_GLOB)):
        manifest = load_manifest_file(manifest_path)
        registry.register(spec_from_manifest(manifest, runtime))
        loaded.append(manifest.name)
    return loaded
