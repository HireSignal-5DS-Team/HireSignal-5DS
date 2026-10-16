"""Freeze the inputs of the soft prompt experiment: val prompts (with their RAG refs) and a manifest with hashes,
held-out case_ids and a leakage audit. Training data is finetune/data/sft_train.jsonl, unchanged.

  HIRESIGNAL_RAG_DIR=<checkout of rag/ from claude/gracious-fermi-ncuem4> python -m prompt_tuning.prepare_data

The val prompts are rendered by matcher.prompt with the same BM25 knowledge as the team evaluation; the script asserts
they are byte-identical to the prompts in finetune/data/sft_val.jsonl. The locked test split is read only for its
case_ids and CV texts (audit); none of its content is written out.
"""
import argparse
import json
import re

from matcher import prompt
from matcher.schemas import CV, Requirement

from .common import BENCH, MANIFEST, SFT_TRAIN, SFT_VAL, VAL_PROMPTS, read_jsonl, sha256


def ngrams(text, n=6):
    w = re.findall(r"\w+", text.lower())
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


def audit(train_cases, held_cases):
    train_cv = {c["cv"]["text"] for c in train_cases}
    train_req = {r["text"].strip().lower() for c in train_cases for r in c["job"]["requirements"]}
    train_ng = [ngrams(c["cv"]["text"]) for c in train_cases]
    jac = []
    for c in held_cases:
        g = ngrams(c["cv"]["text"])
        jac.append(max((len(g & t) / len(g | t) if g | t else 0.0) for t in train_ng))
    return {"cases": len(held_cases),
            "case_id_overlap": len({c["case_id"] for c in train_cases} & {c["case_id"] for c in held_cases}),
            "exact_cv_duplicates": sum(c["cv"]["text"] in train_cv for c in held_cases),
            "requirement_text_overlap": sum(r["text"].strip().lower() in train_req
                                            for c in held_cases for r in c["job"]["requirements"]),
            "max_cv_jaccard_6gram": round(max(jac), 4) if jac else 0.0}


def val_prompts(val_cases, knowledge, k=3):
    for c in val_cases:
        cv = CV(**c["cv"])
        for r in c["job"]["requirements"]:
            req = Requirement(**r)
            refs = knowledge.lookup(req, k=k)
            yield {"case_id": c["case_id"], "req_id": req.req_id, "refs": [x.model_dump() for x in refs],
                   "messages": prompt.messages(cv, req, refs)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--k", type=int, default=3)
    a = ap.parse_args(argv)
    from matcher.knowledge import RagKnowledge

    train, val, test = (read_jsonl(BENCH / f"{s}.jsonl") for s in ("train", "val", "test"))
    vp = list(val_prompts(val, RagKnowledge(), a.k))
    sft_val = {(e["case_id"], e["req_id"]): e["messages"][:2] for e in read_jsonl(SFT_VAL)}
    diff = [(p["case_id"], p["req_id"]) for p in vp if sft_val.get((p["case_id"], p["req_id"])) != p["messages"]]
    assert not diff and len(vp) == len(sft_val), f"val prompts differ from sft_val.jsonl: {diff[:3]}"
    VAL_PROMPTS.parent.mkdir(parents=True, exist_ok=True)
    VAL_PROMPTS.write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in vp), encoding="utf-8")
    sft_train = read_jsonl(SFT_TRAIN)
    m = {"dataset_version": json.loads((BENCH / "MANIFEST.json").read_text())["version"],
         "prompt_version": prompt.PROMPT_VERSION, "knowledge": "rag.bm25", "k": a.k,
         "files": {"finetune/data/sft_train.jsonl": {"sha256": sha256(SFT_TRAIN), "examples": len(sft_train),
                                                     "use": "TRAINING (the only file the soft prompt sees)"},
                   "finetune/data/sft_val.jsonl": {"sha256": sha256(SFT_VAL), "examples": len(sft_val),
                                                   "use": "val loss for checkpoint selection only"},
                   "prompt_tuning/data/val_prompts.jsonl": {"sha256": sha256(VAL_PROMPTS), "prompts": len(vp),
                                                            "use": "EVALUATION ONLY (no targets)"},
                   "benchmark/data/val.jsonl": {"sha256": sha256(BENCH / "val.jsonl"), "use": "gold for scoring"}},
         "val_case_ids": sorted({c["case_id"] for c in val}), "test_case_ids": sorted({c["case_id"] for c in test}),
         "train_case_ids_in_sft": sorted({e["case_id"] for e in sft_train}),
         "leakage_audit": {"val": audit(train, val), "test": audit(train, test)},
         "never_train": ["benchmark/data/val.jsonl", "benchmark/data/test.jsonl (locked, not bundled)"]}
    MANIFEST.write_text(json.dumps(m, indent=2) + "\n")
    print(json.dumps({k: v for k, v in m.items() if k.endswith("audit") or k == "files"}, indent=2))


if __name__ == "__main__":
    main()
