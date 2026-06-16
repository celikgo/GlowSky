"""The design-loop orchestrator (Phase 0 vertical slice).

Implements the architecture's core pattern: the LLM *plans and explains*; validated
deterministic tools *compute*. Every chemistry call now goes through the
ToolExecutionService (docs/13) — so the orchestrator is agnostic to whether a tool
ran inline, on a CPU/GPU worker, or hit a cache. Flow:

  validate seed -> [LLM] propose plan -> generate analogs -> profile each
  -> filter by constraints -> rank -> [LLM] synthesize explanation
"""
from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from services.agent.schemas import (
    Candidate,
    DesignConstraints,
    DesignPlan,
    DesignRunResult,
    ToolCallRecord,
)
from services.llm_gateway.gateway import LLMGateway
from services.llm_gateway.types import CompletionRequest, TaskClass
from services.tools.catalog import build_default_registry
from services.tools.context import ExecutionContext
from services.tools.executor import ToolExecutionService

_PLAN_SYSTEM = (
    "You are a medicinal-chemistry design planner. Given a natural-language goal, "
    "respond with ONLY a JSON object with keys: max_analogs (int), constraints "
    "(object with optional mw_max, logp_min, logp_max, exclude_pains, require_lipinski), "
    "and rationale (string). Do not include any prose outside the JSON."
)


class DesignOrchestrator:
    def __init__(
        self,
        gateway: LLMGateway | None = None,
        executor: ToolExecutionService | None = None,
    ) -> None:
        self._gw = gateway or LLMGateway()
        self._exec = executor or ToolExecutionService(build_default_registry())

    async def _propose_plan(self, goal: str) -> DesignPlan:
        req = CompletionRequest(
            messages=[
                {"role": "system", "content": _PLAN_SYSTEM},
                {"role": "user", "content": goal},
            ],
            task_class=TaskClass.REASONING,
            metadata={"mock_intent": "design_plan", "goal": goal},
        )
        resp = await self._gw.complete(req)
        try:
            return DesignPlan(**json.loads(resp.text))
        except Exception:
            return DesignPlan(rationale="fallback plan (model returned unparseable JSON)")

    @staticmethod
    def _passes(props: dict, c: DesignConstraints) -> bool:
        if c.mw_max is not None and props["mw"] > c.mw_max:
            return False
        if c.logp_min is not None and props["logp"] < c.logp_min:
            return False
        if c.logp_max is not None and props["logp"] > c.logp_max:
            return False
        if c.exclude_pains and props.get("has_pains"):
            return False
        if c.require_lipinski and not props.get("lipinski_pass"):
            return False
        return True

    async def _explain(self, plan: DesignPlan, candidates: list[Candidate]) -> str:
        kept = [c for c in candidates if c.passed_filters]
        summary = "\n".join(
            f"{c.modification} {c.smiles} (MW {c.properties['mw']}, "
            f"logP {c.properties['logp']}, QED {c.properties['qed']})"
            for c in kept[:5]
        )
        req = CompletionRequest(
            messages=[
                {"role": "system", "content": "Summarize the analog design results for a chemist."},
                {"role": "user", "content": f"Goal constraints: {plan.constraints}\n{summary}"},
            ],
            task_class=TaskClass.FAST_TRIAGE,
            metadata={
                "mock_intent": "synthesize",
                "n_candidates": len(candidates),
                "n_kept": len(kept),
                "top": [c.model_dump() for c in kept[:3]],
            },
        )
        return (await self._gw.complete(req)).text

    async def run(
        self,
        goal: str,
        seed_smiles: str,
        ctx: ExecutionContext | None = None,
        emit: Callable[[dict], Awaitable[None]] | None = None,
    ) -> DesignRunResult:
        """Run the design loop.

        If ``emit`` is given, each milestone is pushed to it as a JSON-able event as it
        happens (started, trace, plan, candidate, ranked, explanation) — this is what the
        streaming Composer subscribes to. The fully assembled result is still returned, so
        non-streaming callers are unaffected.
        """
        ctx = ctx or ExecutionContext()

        async def _emit(event: dict) -> None:
            if emit is not None:
                await emit(event)

        trace: list[ToolCallRecord] = []
        step = 0

        def record(res, *, input: dict, summary: str, calls: int = 1) -> ToolCallRecord:
            nonlocal step
            step += 1
            r = res.record
            rec = ToolCallRecord(
                step=step, tool=r.tool, tool_version=r.version, compute_class=r.compute_class,
                input=input, summary=summary, duration_ms=r.duration_ms,
                cache_hit=r.cache_hit, calls=calls,
            )
            trace.append(rec)
            return rec

        await _emit({"type": "started", "goal": goal, "seed_smiles": seed_smiles})

        # 1. Validate the seed (firewall) ------------------------------------
        seed_res = self._exec.execute("validate_molecule", {"smiles": seed_smiles}, ctx)
        seed = seed_res.output
        rec = record(seed_res, input={"smiles": seed_smiles},
                     summary=f"valid={seed['valid']} -> {seed['canonical_smiles']}")
        await _emit({"type": "trace", "record": rec.model_dump()})
        if not seed["valid"]:
            raise ValueError(f"seed molecule invalid: {seed['error']}")
        parent_smiles = seed["canonical_smiles"]

        # 2. Plan (LLM) ------------------------------------------------------
        plan = await self._propose_plan(goal)
        await _emit({"type": "plan", "parent_smiles": parent_smiles, "plan": plan.model_dump()})

        # 3. Generate analogs (deterministic tool) ---------------------------
        gen_res = self._exec.execute(
            "generate_analogs",
            {"canonical_smiles": parent_smiles, "max_analogs": plan.max_analogs}, ctx,
        )
        analogs = gen_res.output
        rec = record(gen_res, input={"canonical_smiles": parent_smiles, "max_analogs": plan.max_analogs},
                     summary=f"generated {len(analogs)} validated analogs")
        await _emit({"type": "trace", "record": rec.model_dump()})

        # 4. Profile + 5. filter + rank --------------------------------------
        candidates: list[Candidate] = []
        profile_ms = 0.0
        cache_hits = 0
        for a in analogs:
            res = self._exec.execute("profile_molecule", {"canonical_smiles": a["smiles"]}, ctx)
            props = res.output
            profile_ms += res.record.duration_ms
            cache_hits += int(res.record.cache_hit)
            passed = self._passes(props, plan.constraints)
            cand = Candidate(
                smiles=a["smiles"], inchikey=a["inchikey"], modification=a["modification"],
                properties=props, passed_filters=passed, score=props["qed"],
            )
            candidates.append(cand)
            # Stream each candidate the moment it's profiled (generation order).
            await _emit({"type": "candidate", "candidate": cand.model_dump()})
        candidates.sort(key=lambda c: (c.passed_filters, c.score), reverse=True)
        if analogs:
            # One aggregate trace entry for the N per-analog profile calls (readability).
            step += 1
            agg = ToolCallRecord(
                step=step, tool="profile_molecule", tool_version="0.1.0",
                compute_class="cpu_light", input={"count": len(analogs)},
                summary=f"profiled {len(candidates)}; "
                f"{sum(c.passed_filters for c in candidates)} passed filters "
                f"({cache_hits} cache hits)",
                duration_ms=round(profile_ms, 3), cache_hit=cache_hits == len(analogs),
                calls=len(analogs),
            )
            trace.append(agg)
            await _emit({"type": "trace", "record": agg.model_dump()})
            # Tell the UI the final ranking so it can reorder the streamed cards.
            await _emit({"type": "ranked", "order": [c.inchikey for c in candidates]})

        # 6. Synthesize explanation (LLM) ------------------------------------
        explanation = await self._explain(plan, candidates)
        await _emit({"type": "explanation", "text": explanation})

        return DesignRunResult(
            goal=goal, parent_smiles=parent_smiles, plan=plan, candidates=candidates,
            trace=trace, explanation=explanation,
            models_used={
                "reasoning": self._gw.route_for(TaskClass.REASONING),
                "fast_triage": self._gw.route_for(TaskClass.FAST_TRIAGE),
            },
        )
