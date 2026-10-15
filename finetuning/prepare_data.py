"""Build the Qwen3-4B-Instruct-2507 SFT files from the APPROVED training data only, and audit leakage.

Approved for training: benchmark/data/train.jsonl (bench-v1, fully synthetic, 150 cases / 681 requirements).
Reserved, never used for training: benchmark/data/val.jsonl (the 202 validation requirements) and
benchmark/data/test.jsonl (sealed final test, 199 requirements).

Outputs (finetuning/data/):
  sft_train.jsonl   train cases with index % 5 != 0  -> training
  sft_dev.jsonl     train cases with index % 5 == 0  -> eval loss / early stopping (still train split)
  val_prompts.jsonl EVALUATION ONLY: val prompts (no targets) for the post-training comparison
  manifest.json     sha256, counts, label distribution, leakage audit
Each SFT line: {"case_id","req_id","messages":[system,user,assistant]} built by matcher.prompt (the exact inference
prompt, with the same 3 BM25 ESCO references) and the gold target {"decision","basis","evidence","explanation"}.
Gold labels are from the generator; explanations are one fixed sentence per decision/basis (no rationales exist).

  HIRESIGNAL_RAG_DIR=<rag dir> python -m finetuning.prepare_data
"""
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from benchmark.run import DATA, read_jsonl
from finetune.build_sft import examples, refuse_test
from finetune.train_judge import is_dev
from matcher import prompt
from matcher.knowledge import RagKnowledge
from matcher.schemas import CV, Requirement

OUT = Path(__file__).parent / "data"


def norm(t):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", " ", t.lower())).strip()


def shingles(t, n=6):
    w = norm(t).split()
    return {" ".join(w[i:i + n]) for i in range(max(1, len(w) - n + 1))}


def leakage(train, others):
    """Exact and near-duplicate checks between training cases and val/test cases."""
    rep = {}
    tr_cv = {norm(c["cv"]["text"]) for c in train}
    tr_req = {norm(r["text"]) for c in train for r in c["job"]["requirements"]}
    tr_lines = {norm(ln) for c in train for ln in c["cv"]["text"].splitlines() if len(ln) > 25}
    tr_sh = [shingles(c["cv"]["text"]) for c in train]
    for name, cases in others.items():
        sims = []
        for c in cases:
            s = shingles(c["cv"]["text"])
            sims.append(max(len(s & t) / len(s | t) for t in tr_sh))
        rep[name] = {
            "cases": len(cases),
            "exact_cv_duplicates": sum(norm(c["cv"]["text"]) in tr_cv for c in cases),
            "exact_requirement_text_overlap": sum(norm(r["text"]) in tr_req for c in cases for r in c["job"]["requirements"]),
            "exact_cv_line_overlap (len>25)": sum(norm(ln) in tr_lines for c in cases for ln in c["cv"]["text"].splitlines() if len(ln) > 25),
            "near_duplicate_cv_max_jaccard_6gram": round(max(sims), 3),
            "near_duplicate_cv_mean_jaccard_6gram": round(sum(sims) / len(sims), 3),
            "cvs_with_jaccard_ge_0.5": sum(x >= 0.5 for x in sims),
        }
    return rep


def write(path, rows):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    train = read_jsonl(DATA / "train.jsonl")
    refuse_test("train", DATA / "train.jsonl", train, DATA / "test.jsonl")  # split field, name and test case ids
    val, test = read_jsonl(DATA / "val.jsonl"), read_jsonl(DATA / "test.jsonl")
    rag = RagKnowledge()
    ex = list(examples(train, rag))
    sft_train = [e for e in ex if not is_dev(e["case_id"])]
    sft_dev = [e for e in ex if is_dev(e["case_id"])]
    val_prompts = []
    for c in val:
        for r in c["job"]["requirements"]:
            refs = rag.lookup(Requirement(**r), k=3)
            val_prompts.append({"case_id": c["case_id"], "req_id": r["req_id"], "refs": [x.model_dump() for x in refs],
                                "messages": prompt.messages(CV(**c["cv"]), Requirement(**r), refs)})
    held = {(c["case_id"], r["req_id"]) for c in val + test for r in c["job"]["requirements"]}
    assert not {(e["case_id"], e["req_id"]) for e in ex} & held, "val/test requirement in training data"
    lab = lambda rows: dict(Counter(json.loads(e["messages"][-1]["content"])["decision"] for e in rows))  # noqa: E731
    manifest = {
        "source": "benchmark/data/train.jsonl (bench-v1, synthetic, generator benchmark/make_dataset.py, seed 20261015)",
        "source_sha256": hashlib.sha256((DATA / "train.jsonl").read_bytes()).hexdigest(),
        "prompt_version": prompt.PROMPT_VERSION, "knowledge": "rag.bm25 (ESCO ICT subset), k=3",
        "files": {
            "sft_train.jsonl": {"sha256": write(OUT / "sft_train.jsonl", sft_train), "examples": len(sft_train),
                                "cases": len({e['case_id'] for e in sft_train}), "decisions": lab(sft_train)},
            "sft_dev.jsonl": {"sha256": write(OUT / "sft_dev.jsonl", sft_dev), "examples": len(sft_dev),
                              "cases": len({e['case_id'] for e in sft_dev}), "decisions": lab(sft_dev)},
            "val_prompts.jsonl": {"sha256": write(OUT / "val_prompts.jsonl", val_prompts), "prompts": len(val_prompts),
                                  "use": "EVALUATION ONLY - never train on it; gold labels stay in benchmark/data/val.jsonl"},
        },
        "reserved_never_train": {"val": "benchmark/data/val.jsonl (45 cases / 202 requirements)",
                                 "test": "benchmark/data/test.jsonl (45 cases / 199 requirements, sealed)"},
        "leakage_audit": leakage(train, {"val": val, "test": test}),
        "privacy": "fully synthetic, anonymised by construction: no real person, name, e-mail or employer",
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({k: v for k, v in manifest.items() if k in ("files", "leakage_audit")}, indent=2))


if __name__ == "__main__":
    main()
