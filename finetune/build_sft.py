"""Build chat SFT jsonl from benchmark cases, using matcher.prompt as the ONLY prompt/target format.

Each output line: {"case_id", "req_id", "messages": [system, user, assistant(target)]}.
The test split is refused three ways: split name, file path, and case_ids listed in the test file.

  python -m finetune.build_sft --split train --knowledge rag
  python -m finetune.build_sft --split val   --knowledge rag
"""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from matcher import prompt
from matcher.schemas import CV, ModelAnswer, Requirement

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "benchmark/data"

# Gold labels carry no explanation; the target needs one (ModelAnswer), so it is a fixed sentence per decision/basis.
EXPLANATIONS = {
    ("MET", "supported"): "The CV directly shows this requirement; the quote is copied from the CV.",
    ("MISSING", "contradicted"): "The CV shows this requirement is not met; the quote is copied from the CV.",
    ("MISSING", "not_documented"): "The CV says nothing about this requirement.",
    ("UNCERTAIN", "ambiguous"): "The CV only partly or indirectly addresses this requirement.",
}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def refuse_test(split, path, rows, test_file):
    """Hard stop if anything about this input looks like the locked test split."""
    path = Path(path).resolve()
    assert split != "test", "refusing to build SFT data from the test split"
    assert "test" not in path.stem.lower(), f"refusing a file whose name looks like the test split: {path}"
    if test_file and Path(test_file).exists():
        assert path != Path(test_file).resolve(), f"refusing the test file itself: {path}"
        test_ids = {r["case_id"] for r in read_jsonl(test_file)}
    else:
        test_ids = set()
    leaked = [r["case_id"] for r in rows if r["case_id"] in test_ids]
    assert not leaked, f"refusing: {len(leaked)} case_ids are in the test split, e.g. {leaked[:3]}"
    bad = [r["case_id"] for r in rows if r.get("split", split) != split]
    assert not bad, f"refusing: rows whose split field is not {split!r}, e.g. {bad[:3]}"
    return len(test_ids)


def knowledge_provider(name):
    from matcher.knowledge import NoKnowledge, RagKnowledge

    return RagKnowledge() if name == "rag" else NoKnowledge()


def examples(rows, knowledge, k=3):
    for row in rows:
        cv = CV(**row["cv"])
        for r in row["job"]["requirements"]:
            req = Requirement(**r)
            g = row["gold"][req.req_id]
            answer = ModelAnswer(decision=g["decision"], basis=g["basis"], evidence=g.get("evidence", [])[:3],
                                 explanation=g.get("explanation") or EXPLANATIONS[(g["decision"], g["basis"])])
            msgs = prompt.messages(cv, req, knowledge.lookup(req, k=k))
            yield {"case_id": row["case_id"], "req_id": req.req_id, "family": row.get("family"),
                   "messages": [*msgs, {"role": "assistant", "content": prompt.target(answer)}]}


def build(split, src, out_dir, knowledge="rag", test_file=DATA / "test.jsonl", k=3):
    rows = read_jsonl(src)
    n_test_ids = refuse_test(split, src, rows, test_file)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"sft_{split}.jsonl"
    exs = list(examples(rows, knowledge_provider(knowledge), k))
    out.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in exs), encoding="utf-8")
    meta = {
        "split": split, "source": str(Path(src).resolve()), "source_sha256": sha256(src),
        "output": str(out.resolve()), "output_sha256": sha256(out), "n_cases": len(rows), "n_examples": len(exs),
        "decisions": dict(Counter(json.loads(e["messages"][-1]["content"])["decision"] for e in exs)),
        "families": dict(Counter(e["family"] for e in exs)), "prompt_version": prompt.PROMPT_VERSION,
        "knowledge": knowledge, "k": k, "test_file": str(test_file), "test_case_ids_checked": n_test_ids,
    }
    (out_dir / f"sft_{split}.meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return meta


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", required=True, choices=["train", "val"])
    ap.add_argument("--src", help="default benchmark/data/<split>.jsonl")
    ap.add_argument("--out-dir", default=str(ROOT / "finetune/data"))
    ap.add_argument("--knowledge", default="rag", choices=["rag", "none"], help="must match the benchmark setting")
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--test-file", default=str(DATA / "test.jsonl"))
    a = ap.parse_args()
    print(json.dumps(build(a.split, a.src or DATA / f"{a.split}.jsonl", a.out_dir, a.knowledge, a.test_file, a.k), indent=2))


if __name__ == "__main__":
    main()
