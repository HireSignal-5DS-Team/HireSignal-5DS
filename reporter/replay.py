"""Pipeline outputs built from REAL saved LoRA Matcher outputs (val only, no new Matcher call).

The LIVE E2E run `rag_opt/results/e2e/lora__gated` stores, for each val requirement, the raw text the fine-tuned
Qwen3-4B LoRA Matcher returned (llama.cpp, Q4_K_M, prompt p1, knowledge rag.gated.v1) and its provenance.
ReplayBackend returns that raw text for the same (case, requirement), so the current pipeline (strict parse, validator
v2, bias auditor, aggregator) runs on genuine model outputs. Each result's provenance says `replayed_from`.
The knowledge refs are rebuilt with the same provider and checked against the saved rag_refs.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "rag_opt/results/e2e/lora__gated"


class ReplayBackend:
    def __init__(self, run_dir=RUN, case_id=None):
        self.run_dir = Path(run_dir)
        self.case_id = case_id
        self.saved = {}
        for p in map(json.loads, (self.run_dir / "predictions.jsonl").read_text().splitlines()):
            if not p["case_id"].startswith("val-"):
                raise ValueError(f"replay is val-only; found {p['case_id']}")
            self.saved[(p["case_id"], p["req_id"])] = p
        self.last_call, self.ref_mismatch = {}, []
        from matcher.factory import model_provenance

        run_prov = json.loads((self.run_dir / "provenance.json").read_text())
        run_cfg = json.loads((self.run_dir / "config.json").read_text())
        if run_cfg.get("split") != "val":
            raise ValueError("replay is val-only")
        pinned, _, _ = model_provenance({})
        if (run_prov.get("adapter") or {}).get("sha") != pinned["adapter"]["sha"]:
            raise ValueError("the saved run used another adapter than the pinned one")
        aliases = [m["id"] for m in run_prov["server_models"]["data"]]
        # the run's own provenance (served alias listed by /v1/models, adapter sha, prompt) + the pinned weights
        self.provenance = {**pinned, "served_alias": aliases[0], "served_aliases": aliases, "alias_verified": True,
                           "prompt_id": run_cfg["backend"]["prompt_version"], "endpoint": run_cfg["backend"]["base_url"],
                           "replayed_from": str(self.run_dir.relative_to(ROOT)),
                           "run_git_commit": run_prov.get("git_commit"), "dataset_sha256": run_prov.get("dataset_sha256")}

    def info(self):
        return {"backend": "replay-of-live", "label": f"replay {self.run_dir.relative_to(ROOT)}", "is_model": True}

    def generate(self, task):
        p = self.saved[(self.case_id, task.req.req_id)]
        if [r.source_id for r in task.refs] != p["rag_refs"]:
            self.ref_mismatch.append(task.req.req_id)
        call = p["call"]
        self.last_call = {"used": "primary", "model": self.provenance["served_alias"], "latency_s": call.get("latency_s"),
                          "error": call.get("error"), "finish_reason": call.get("finish_reason"),
                          "provenance": dict(self.provenance)}
        return p["raw"]


def val_cases():
    return {c["case_id"]: c for c in map(json.loads, (ROOT / "benchmark/data/val.jsonl").read_text().splitlines())}


def pipeline_output(case_id, judge=None, cases=None, knowledge=None):
    """Pipeline.run() output for one val case from the saved LIVE LoRA raw outputs."""
    from matcher.factory import bias_auditor, model_provenance
    from matcher.knowledge import GatedKnowledge
    from matcher.pipeline import Pipeline

    if not case_id.startswith("val-"):
        raise ValueError("val cases only")
    c = (cases or val_cases())[case_id]
    be = ReplayBackend(case_id=case_id)
    _, _, cfg = model_provenance({})
    pipe = Pipeline(be, knowledge or GatedKnowledge(), judge=judge, auditor=bias_auditor({}, cfg))
    out = pipe.run(c["cv"], c["job"])
    if be.ref_mismatch:
        raise RuntimeError(f"{case_id}: rebuilt knowledge refs differ from the LIVE run for {be.ref_mismatch}")
    return out, c["job"].get("title")
