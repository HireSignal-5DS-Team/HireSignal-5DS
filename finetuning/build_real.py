"""Turn human-labelled Djinni review files into Matcher training, dev and real-eval data, and audit leakage.

Input: one or more labelled copies of djinni_review.xlsx (sample_djinni.py). Only rows a human labelled count; every
label is checked against the Matcher contract (decision/basis pairs, exact CV quotes). Problems go to
label_errors.csv for the labeller to fix; nothing is silently repaired. When two labellers label the same req_id,
Cohen's kappa is reported and disagreements are left out (disagreements.csv).

Splits are by pair (one CV + one job per pair): 20 % eval_real (never trained on), 10 % dev, 70 % train.
Optional --extra FILE:SHARE adds already-built SFT files (ContractNLI, synthetic bench-v1 train) to TRAIN only,
capped at SHARE of the final train set.

Outputs in --out (keep outside git, it holds CV text):
  sft_train.jsonl, sft_dev.jsonl            {"case_id","req_id","source","messages":[system,user,assistant]}
  eval/real_cases.jsonl                     gold for the real eval split (benchmark case format)
  eval/{val,real}_{rag,none}_prompts.jsonl  prompts for the A-D comparison (no targets)
  manifest.json                             counts, sha256, label provenance, agreement, leakage audit

  PYTHONPATH=<deps> HIRESIGNAL_RAG_DIR=<deps>/rag python -m finetuning.build_real --labels a.xlsx [b.xlsx] --out <dir>
"""
import argparse
import csv
import hashlib
import json
import random
import re
from collections import Counter
from pathlib import Path

import pandas as pd

from finetune.build_sft import examples
from matcher import prompt
from matcher.knowledge import NoKnowledge, RagKnowledge
from matcher.schemas import CV, Requirement
from matcher.validate import CONSISTENT, find_span

SEED = 13
CATEGORIES = {"skill", "experience", "education", "certification", "language", "other"}
SEP = "||"


def cell(v):
    return "" if v is None or (isinstance(v, float) and v != v) else str(v).strip()


def split_of(pair_id):
    b = int(hashlib.sha1(pair_id.encode()).hexdigest(), 16) % 10
    return "eval_real" if b < 2 else "dev" if b == 2 else "train"


def check(row, cv_text):
    """Return (label dict, None) or (None, error text) for one labelled requirement row."""
    dec, basis = cell(row["decision"]).upper(), cell(row["basis"]).lower()
    quotes = [q.strip() for q in cell(row["evidence"]).split(SEP) if q.strip()]
    text, cat = cell(row["text"]), cell(row["category"]).lower() or "skill"
    if dec not in CONSISTENT:
        return None, f"decision must be MET, MISSING or UNCERTAIN, got {dec!r}"
    if basis not in CONSISTENT[dec]:
        return None, f"{dec} cannot have basis {basis!r}; allowed: {sorted(CONSISTENT[dec])}"
    if not text:
        return None, "requirement text is empty"
    if cat not in CATEGORIES:
        return None, f"category {cat!r} not in {sorted(CATEGORIES)}"
    if len(quotes) > 3:
        return None, "more than 3 evidence quotes"
    missing = [q for q in quotes if find_span(cv_text, q) is None]
    if missing:
        return None, f"evidence not found word for word in the CV: {missing[0][:80]!r}"
    if basis in ("supported", "contradicted") and not quotes:
        return None, f"{dec}+{basis} needs at least one exact CV quote"
    if basis == "not_documented" and quotes:
        return None, "not_documented must have empty evidence"
    expl = cell(row["explanation"])
    if len(expl) > 600:
        return None, "explanation longer than 600 characters"
    mny = cell(row["min_years"])
    return {"decision": dec, "basis": basis, "evidence": quotes, "explanation": expl,
            "text": text, "kind": "nice" if cell(row["kind"]).lower() == "nice" else "must", "category": cat,
            "min_years": float(mny) if mny else None, "source": cell(row["source"]),
            "labeller": cell(row["labeller"]) or "?"}, None


def kappa(a, b):
    n = len(a)
    if not n:
        return None
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in ca) / n / n
    return round((po - pe) / (1 - pe), 3) if pe < 1 else 1.0


def load_labels(paths):
    pairs, rows, errors = {}, [], []
    for p in paths:
        for _, r in pd.read_excel(p, sheet_name="pairs").iterrows():
            pairs.setdefault(r["pair_id"], r.to_dict())
        for _, r in pd.read_excel(p, sheet_name="requirements").iterrows():
            r = r.to_dict()
            keep = cell(r.get("keep_requirement")).lower()
            if keep == "no" or (not cell(r["decision"]) and keep in ("", "yes", "edit")):
                continue  # dropped or not labelled yet
            lab, err = check(r, cell(pairs[r["pair_id"]]["cv_text"]))
            if err:
                errors.append({"file": Path(p).name, "req_id": r["req_id"], "labeller": cell(r.get("labeller")), "error": err})
            else:
                rows.append({**lab, "pair_id": r["pair_id"], "req_id": r["req_id"]})
    return pairs, rows, errors


def resolve(rows):
    """One gold label per req_id; double-labelled items count only when decision and basis agree."""
    by = {}
    for r in rows:
        by.setdefault(r["req_id"], []).append(r)
    gold, dis, a, b = {}, [], [], []
    for rid, labs in by.items():
        labs = list({x["labeller"]: x for x in labs}.values())  # one vote per labeller
        if len(labs) == 1:
            gold[rid] = labs[0]
            continue
        a.append(labs[0]["decision"]), b.append(labs[1]["decision"])
        if len({(x["decision"], x["basis"]) for x in labs}) == 1:
            gold[rid] = labs[0]
        else:
            dis.append({"req_id": rid, **{f"{x['labeller']}": f"{x['decision']}/{x['basis']}" for x in labs}})
    return gold, dis, {"double_labelled": len(a), "decision_kappa": kappa(a, b),
                       "agreement": round(sum(x == y for x, y in zip(a, b)) / len(a), 3) if a else None}


def cases_from(pairs, gold):
    out = {}
    for rid, g in sorted(gold.items()):
        p = pairs[g["pair_id"]]
        c = out.setdefault(g["pair_id"], {
            "case_id": g["pair_id"], "split": split_of(g["pair_id"]), "source": "djinni",
            "cv": {"cv_id": cell(p["cv_id"]), "text": cell(p["cv_text"])},
            "job": {"job_id": cell(p["job_id"]), "title": cell(p["job_title"]), "requirements": []}, "gold": {}})
        c["job"]["requirements"].append({"req_id": rid, "text": g["text"], "kind": g["kind"], "category": g["category"],
                                         "skill_terms": [], "min_years": g["min_years"]})
        c["gold"][rid] = {"decision": g["decision"], "basis": g["basis"], "evidence": g["evidence"],
                          "explanation": g["explanation"], "labeller": g["labeller"],
                          "tags": [g["category"], g["kind"], f"{g['decision']}+{g['basis']}", g["source"]]}
    return list(out.values())


def norm(t):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", " ", t.lower())).strip()


def shingles(t, n=6):
    w = norm(t).split()
    return {" ".join(w[i:i + n]) for i in range(max(1, len(w) - n + 1))}


def near_dup(a, others):
    s = shingles(a)
    return max((len(s & t) / len(s | t) for t in others), default=0.0)


def leakage(train, held):
    tr_sh = [shingles(c["cv"]["text"]) for c in train]
    tr_req = {norm(r["text"]) for c in train for r in c["job"]["requirements"]}
    rep = {}
    for name, cases in held.items():
        sims = [near_dup(c["cv"]["text"], tr_sh) for c in cases]
        rep[name] = {"cases": len(cases),
                     "exact_cv_duplicates": sum(norm(c["cv"]["text"]) in {norm(t["cv"]["text"]) for t in train} for c in cases),
                     "requirement_text_overlap": sum(norm(r["text"]) in tr_req for c in cases for r in c["job"]["requirements"]),
                     "max_cv_jaccard_6gram": round(max(sims, default=0.0), 3),
                     "cvs_with_jaccard_ge_0.5": sum(x >= 0.5 for x in sims)}
    return rep


def read_jsonl(path):
    return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]


def write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        if rows:
            w = csv.DictWriter(f, fieldnames=sorted({k for r in rows for k in r}))
            w.writeheader()
            w.writerows(rows)


def prompts(cases, knowledge):
    out = []
    for c in cases:
        for r in c["job"]["requirements"]:
            req = Requirement(**r)
            refs = knowledge.lookup(req, k=3)
            out.append({"case_id": c["case_id"], "req_id": r["req_id"], "refs": [x.model_dump() for x in refs],
                        "messages": prompt.messages(CV(**c["cv"]), req, refs)})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--val", required=True, help="benchmark/data/val.jsonl (evaluation prompts only)")
    ap.add_argument("--test", help="benchmark/data/test.jsonl: read ONLY for the leakage audit")
    ap.add_argument("--extra", nargs="*", default=[], help="FILE:SHARE, e.g. contractnli_sft.jsonl:0.25")
    ap.add_argument("--knowledge", choices=["rag", "none"], default="rag", help="knowledge block in training prompts")
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    pairs, rows, errors = load_labels(a.labels)
    gold, dis, agree = resolve(rows)
    write_csv(out / "label_errors.csv", errors)
    write_csv(out / "disagreements.csv", dis)
    cases = cases_from(pairs, gold)
    by = {s: [c for c in cases if c["split"] == s] for s in ("train", "dev", "eval_real")}
    # a train/dev CV that nearly duplicates an eval CV would leak; move it out of training
    ev_sh = [shingles(c["cv"]["text"]) for c in by["eval_real"]]
    dropped = [c["case_id"] for s in ("train", "dev") for c in by[s] if near_dup(c["cv"]["text"], ev_sh) >= 0.5]
    for s in ("train", "dev"):
        by[s] = [c for c in by[s] if c["case_id"] not in dropped]

    rag = RagKnowledge()  # always needed for the RAG eval prompts
    kn = rag if a.knowledge == "rag" else NoKnowledge()
    sft = {s: [{**e, "source": "djinni"} for e in examples(by[s], kn)] for s in ("train", "dev")}
    n_real = len(sft["train"])
    shares = {p.rsplit(":", 1)[0]: float(p.rsplit(":", 1)[1]) for p in a.extra}
    assert sum(shares.values()) < 1, "extra shares must sum to < 1"
    rng, extra_counts = random.Random(SEED), {}
    for path, share in shares.items():
        assert "test" not in Path(path).stem.lower() and "val" not in Path(path).stem.lower(), f"refusing {path}"
        ex = read_jsonl(path)
        n = min(len(ex), round(share / (1 - sum(shares.values())) * n_real))
        pick = rng.sample(ex, n)
        sft["train"] += [{**e, "source": e.get("source") or Path(path).stem} for e in pick]
        extra_counts[Path(path).name] = n
    rng.shuffle(sft["train"])

    val = read_jsonl(a.val)
    test = read_jsonl(a.test) if a.test else []
    held_ids = {(c["case_id"], r["req_id"]) for c in val + test for r in c["job"]["requirements"]}
    assert not held_ids & {(e["case_id"], e["req_id"]) for e in sft["train"] + sft["dev"]}, "val/test item in training data"

    dec = lambda rs: dict(Counter(json.loads(e["messages"][-1]["content"])["decision"] for e in rs))  # noqa: E731
    files = {f"sft_{s}.jsonl": {"sha256": write(out / f"sft_{s}.jsonl", sft[s]), "examples": len(sft[s]),
                                "by_source": dict(Counter(e["source"] for e in sft[s])), "decisions": dec(sft[s])}
             for s in ("train", "dev")}
    files["eval/real_cases.jsonl"] = {"sha256": write(out / "eval/real_cases.jsonl", by["eval_real"]),
                                      "cases": len(by["eval_real"]),
                                      "requirements": sum(len(c["gold"]) for c in by["eval_real"]),
                                      "decisions": dict(Counter(g["decision"] for c in by["eval_real"] for g in c["gold"].values()))}
    for name, cs in (("val", val), ("real", by["eval_real"])):
        for kname, k in (("rag", rag), ("none", NoKnowledge())):
            f = f"eval/{name}_{kname}_prompts.jsonl"
            ps = prompts(cs, k)
            files[f] = {"sha256": write(out / f, ps), "prompts": len(ps), "use": "EVALUATION ONLY"}
    manifest = {
        "label_files": [Path(p).name for p in a.labels],
        "labels": {"valid": len(rows), "errors": len(errors), "gold_requirements": len(gold),
                   "disagreements_excluded": len(dis), "labellers": dict(Counter(g["labeller"] for g in gold.values())),
                   "provenance": "human labels on real Djinni CV/job text (MIT); pre-labels are never used", **agree},
        "splits_by_pair": {s: len(by[s]) for s in by}, "dropped_near_duplicates_of_eval": dropped,
        "extra_train_sources": extra_counts, "prompt_version": prompt.PROMPT_VERSION,
        "train_knowledge": "rag.bm25 (ESCO ICT), k=3" if a.knowledge == "rag" else "none",
        "files": files,
        "leakage_audit": leakage(by["train"] + by["dev"], {"val": val, "test": test, "eval_real": by["eval_real"]}),
        "never_train": ["benchmark/data/val.jsonl", "benchmark/data/test.jsonl (sealed)", "eval/real_cases.jsonl"],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ("labels", "splits_by_pair", "extra_train_sources")}, indent=1))
    print(f"label errors: {len(errors)} (see {out / 'label_errors.csv'})")


if __name__ == "__main__":
    main()
