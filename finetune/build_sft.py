"""Build SFT examples for LoRA from benchmark/data/train.jsonl (CONTRACT.md format).

One example per requirement: messages = matcher.prompt.messages(cv, req, refs) (the inference prompt, unchanged),
completion = matcher.prompt.target(ModelAnswer(...)). 10% of train CASES (by sha256(case_id)) go to sft_dev.jsonl
for dev loss / early stopping. val.jsonl and test.jsonl are never inputs here.

    python -m finetune.build_sft benchmark/data/train.jsonl [--out-dir finetune/data] [--knowledge rag|none]
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from matcher import prompt  # noqa: E402
from matcher.knowledge import NoKnowledge, RagKnowledge  # noqa: E402
from matcher.schemas import CV, Job, ModelAnswer  # noqa: E402
from matcher.validate import CONSISTENT  # noqa: E402

DEV_FRACTION = 10  # 1 in 10 cases


def _clip(s, n=160):
    return s if len(s) <= n else s[: n - 3] + "..."


def explanation(decision, basis, evidence, req):
    """Short deterministic explanation; gold data has none."""
    q = f'"{_clip(evidence[0])}"' if evidence else None
    yrs = f" ({req.min_years:g}+ years)" if req.min_years else ""
    if decision == "MET":
        text = f"The CV states {q}, which shows the requirement{yrs} is met."
    elif basis == "contradicted":
        text = f"The CV states {q}, which falls short of the requirement{yrs}."
    elif basis == "not_documented":
        text = "The CV does not mention this requirement, so it is not documented."
    else:
        text = (f"The CV only partially or indirectly supports the requirement: {q}." if q
                else "The CV is unclear about this requirement.")
    return text[:600]


def is_dev(case_id):
    return int(hashlib.sha256(case_id.encode()).hexdigest(), 16) % DEV_FRACTION == 0


def make_knowledge(kind):
    return RagKnowledge() if kind == "rag" else NoKnowledge()


def build(train_path, out_dir, knowledge="rag", k=3):
    train_path, out_dir = Path(train_path), Path(out_dir)
    if "test" in train_path.name.lower():
        raise ValueError(f"refusing {train_path}: test data is locked and never used for training")
    if "val" in train_path.name.lower():
        raise ValueError(f"refusing {train_path}: val is for model selection only, not training")
    kb = make_knowledge(knowledge)
    cases = [json.loads(line) for line in train_path.read_text().splitlines() if line.strip()]
    dev_ids = {c["case_id"] for c in cases if is_dev(c["case_id"])}
    if not dev_ids and len(cases) >= 2:  # tiny files: still hold out one case, deterministically
        dev_ids = {min((c["case_id"] for c in cases), key=lambda i: hashlib.sha256(i.encode()).hexdigest())}
    out = {"train": [], "dev": []}
    for c in cases:
        if c.get("split", "train") != "train":
            raise ValueError(f"case {c['case_id']} has split={c.get('split')!r}; only train cases may be used")
        cv, job = CV(**c["cv"]), Job(**c["job"])
        for req in job.requirements:
            g = c["gold"][req.req_id]
            if g["basis"] not in CONSISTENT[g["decision"]]:
                raise ValueError(f"{c['case_id']}/{req.req_id}: inconsistent gold {g['decision']}/{g['basis']}")
            ev = g.get("evidence", [])[:3]
            ans = ModelAnswer(decision=g["decision"], basis=g["basis"], evidence=ev,
                              explanation=explanation(g["decision"], g["basis"], ev, req))
            refs = kb.lookup(req, k=k)
            out["dev" if c["case_id"] in dev_ids else "train"].append({
                "messages": prompt.messages(cv, req, refs), "completion": prompt.target(ans),
                "meta": {"case_id": c["case_id"], "req_id": req.req_id, "decision": g["decision"], "basis": g["basis"],
                         "prompt_version": prompt.PROMPT_VERSION, "knowledge": kb.name,
                         "rag_refs": [r.source_id for r in refs]}})
    out_dir.mkdir(parents=True, exist_ok=True)
    for split, rows in out.items():
        (out_dir / f"sft_{split}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    meta = {"input": str(train_path), "input_sha256": hashlib.sha256(train_path.read_bytes()).hexdigest(),
            "knowledge": kb.name, "k": k, "prompt_version": prompt.PROMPT_VERSION, "n_cases": len(cases),
            "dev_case_ids": sorted(dev_ids), "n_train_examples": len(out["train"]), "n_dev_examples": len(out["dev"])}
    (out_dir / "sft_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return meta


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("train_jsonl")
    ap.add_argument("--out-dir", default=str(Path(__file__).parent / "data"))
    ap.add_argument("--knowledge", choices=["rag", "none"], default="rag",
                    help="rag = BM25 over ESCO (must match inference); none = NoKnowledge, for runs without rag/")
    ap.add_argument("--k", type=int, default=3)
    a = ap.parse_args(argv)
    print(json.dumps(build(a.train_jsonl, a.out_dir, a.knowledge, a.k), indent=2))


if __name__ == "__main__":
    main()
