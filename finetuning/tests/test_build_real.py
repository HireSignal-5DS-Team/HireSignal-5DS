"""End-to-end check of build_real.py on FAKE labels (auto-filled, never used for training).

  PYTHONPATH=<deps> HIRESIGNAL_RAG_DIR=<deps>/rag python -m finetuning.tests.test_build_real <review.xlsx> <val.jsonl> <tmp dir>
"""
import json
import sys
from pathlib import Path

import pandas as pd

from finetuning import build_real


def fake_label(xlsx, out, labeller, broken=0):
    pairs = pd.read_excel(xlsx, sheet_name="pairs")
    reqs = pd.read_excel(xlsx, sheet_name="requirements")
    cv = dict(zip(pairs.pair_id, pairs.cv_text))
    for col in ("keep_requirement", "decision", "basis", "evidence", "explanation", "labeller"):
        reqs[col] = reqs[col].astype(object)
    for i, r in reqs.iterrows():
        word = next((w for w in str(r["text"]).split() if len(w) > 4 and w.lower() in cv[r.pair_id].lower()), None)
        line = next((ln for ln in cv[r.pair_id].splitlines() if word and word.lower() in ln.lower() and ln.strip()), None)
        if line:
            reqs.loc[i, ["decision", "basis", "evidence"]] = ["MET", "supported", line.strip()[:150]]
        else:
            reqs.loc[i, ["decision", "basis", "evidence"]] = ["MISSING", "not_documented", ""]
        reqs.loc[i, ["keep_requirement", "explanation", "labeller"]] = ["yes", "fake label for a pipeline test", labeller]
    for i in range(broken):  # deliberate errors the checker must catch
        reqs.loc[i, ["decision", "basis", "evidence"]] = ["MET", "not_documented", ""] if i % 2 else ["MET", "supported", "text that is not in the CV"]
    with pd.ExcelWriter(out) as xw:
        pairs.to_excel(xw, sheet_name="pairs", index=False)
        reqs.to_excel(xw, sheet_name="requirements", index=False)
    return len(reqs)


def main(xlsx, val, tmp):
    tmp = Path(tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    n = fake_label(xlsx, tmp / "a.xlsx", "AA", broken=4)
    fake_label(xlsx, tmp / "b.xlsx", "BB")
    build_real.main(["--labels", str(tmp / "a.xlsx"), str(tmp / "b.xlsx"), "--out", str(tmp / "build"), "--val", val])
    m = json.loads((tmp / "build/manifest.json").read_text(encoding="utf-8"))
    assert m["labels"]["errors"] == 4, m["labels"]
    assert m["labels"]["double_labelled"] == n - 4 and m["labels"]["decision_kappa"] == 1.0, m["labels"]
    assert m["labels"]["gold_requirements"] == n - 4 + 4  # broken rows in a.xlsx are still labelled correctly in b.xlsx
    ids = {s: {json.loads(x)["case_id"] for x in (tmp / f"build/sft_{s}.jsonl").read_text(encoding="utf-8").splitlines()}
           for s in ("train", "dev")}
    real_eval = {json.loads(x)["case_id"] for x in (tmp / "build/eval/real_cases.jsonl").read_text(encoding="utf-8").splitlines()}
    assert not (ids["train"] | ids["dev"]) & real_eval and not ids["train"] & ids["dev"], "pair leaked across splits"
    ex = json.loads((tmp / "build/sft_train.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert [x["role"] for x in ex["messages"]] == ["system", "user", "assistant"]
    assert m["leakage_audit"]["val"]["exact_cv_duplicates"] == 0
    print("OK", m["splits_by_pair"], m["files"]["sft_train.jsonl"]["decisions"])


if __name__ == "__main__":
    main(*sys.argv[1:4])
