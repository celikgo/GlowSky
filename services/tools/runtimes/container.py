"""Container tool runtime — run a researcher's tool as a sandboxed Docker container.

THE TOOL ABI (the contract a container image must satisfy):
  • The container reads a single JSON object of arguments from STDIN.
  • It writes a single JSON object to STDOUT:
        {"ok": true,  "result": {...}}     on success
        {"ok": false, "error": "message"}  on handled failure
  • Anything on STDERR is treated as diagnostics (surfaced on error).
  • Exit code 0 with a parseable {"ok": true} is the only success path.

SANDBOXING (docs/07 §6, docs/13 §6) — every container runs one-shot with:
  --rm --network none (egress NONE) --read-only --cap-drop ALL
  --security-opt no-new-privileges --pids-limit --memory --cpus
  --tmpfs /tmp (writable scratch) --user (non-root)  + a hard wall-clock timeout.

The runner is injectable so the command construction and parsing are unit-testable
without a Docker daemon.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

from services.tools.spec import Egress, Resources


class ContainerToolError(RuntimeError):
    pass


class DockerUnavailable(ContainerToolError):
    pass


@dataclass
class RunOutcome:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


# A runner takes (argv, stdin_text, timeout_s) and returns a RunOutcome.
Runner = Callable[[list[str], str, int], RunOutcome]


def _subprocess_runner(argv: list[str], stdin_text: str, timeout_s: int) -> RunOutcome:
    try:
        proc = subprocess.run(
            argv, input=stdin_text, capture_output=True, text=True, timeout=timeout_s
        )
        return RunOutcome(proc.returncode, proc.stdout, proc.stderr)
    except subprocess.TimeoutExpired as exc:
        return RunOutcome(124, exc.stdout or "", exc.stderr or "", timed_out=True)


class ContainerRuntime:
    def __init__(self, runner: Runner | None = None, docker_bin: str = "docker") -> None:
        self._runner = runner or _subprocess_runner
        self._docker = docker_bin
        # When a runner is injected (tests), it stands in for the daemon — skip the check.
        self._check_daemon = runner is None

    def available(self) -> bool:
        return shutil.which(self._docker) is not None

    def build_command(
        self, image: str, resources: Resources, egress: Egress, user: str | None
    ) -> list[str]:
        """Construct the sandboxed `docker run` argv. Pure function -> testable."""
        argv = [
            self._docker, "run", "--rm", "--interactive",
            "--read-only",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--pids-limit", "256",
            "--memory", f"{resources.mem_mb}m",
            "--cpus", str(resources.cpu),
            "--tmpfs", "/tmp:rw,size=256m",
        ]
        # Network policy: NONE => fully isolated. ALLOWLIST is a Phase-3 egress proxy.
        if egress == Egress.NONE:
            argv += ["--network", "none"]
        if resources.gpu:
            argv += ["--gpus", str(resources.gpu)]
        if user:
            argv += ["--user", user]
        argv.append(image)
        return argv

    def run(
        self,
        *,
        image: str,
        args: dict,
        resources: Resources,
        egress: Egress = Egress.NONE,
        user: str | None = "65534:65534",
    ) -> dict:
        """Execute the container tool and return its `result` payload."""
        if self._check_daemon and not self.available():
            raise DockerUnavailable(
                f"docker not found ('{self._docker}'); container tools require a Docker daemon"
            )
        argv = self.build_command(image, resources, egress, user)
        outcome = self._runner(argv, json.dumps(args), resources.timeout_s)

        if outcome.timed_out:
            raise ContainerToolError(
                f"container tool '{image}' timed out after {resources.timeout_s}s"
            )
        if outcome.returncode != 0:
            raise ContainerToolError(
                f"container tool '{image}' exited {outcome.returncode}: "
                f"{(outcome.stderr or outcome.stdout)[:500]}"
            )
        return self._parse(image, outcome.stdout)

    @staticmethod
    def _parse(image: str, stdout: str) -> dict:
        try:
            payload = json.loads(stdout.strip().splitlines()[-1]) if stdout.strip() else {}
        except (json.JSONDecodeError, IndexError) as exc:
            raise ContainerToolError(
                f"container tool '{image}' produced non-JSON output: {stdout[:200]!r}"
            ) from exc
        if not payload.get("ok"):
            raise ContainerToolError(
                f"container tool '{image}' reported failure: {payload.get('error', 'unknown')}"
            )
        return payload.get("result", {})
