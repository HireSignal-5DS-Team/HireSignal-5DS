"""Replay the saved raw Matcher outputs of the E2E arms through the CURRENT matcher/validate.py (no model call).

    python -m rag_opt.replay_validator --root rag_opt/results/e2e [--label v1|v2] [--out stem]

Unlike docs/qa/analysis/replay_validator.py (which rebuilds refs from the full ESCO text), each arm's references are
rebuilt with the provider that produced them (none -> [], bm25 -> legacy RagKnowledge, gated -> GatedKnowledge), so
the validator sees exactly the KnowledgeRef objects of the live run (same compact text and shown aliases). The
rebuilt ids are checked against the saved rag_refs. Paired statistics as in rag_opt/e2e_report.py.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from matcher.knowledge import GatedKnowledge, NoKnowledge, RagKnowledge  # noqa: E402
from matcher.schemas import CV, Requirement  # noqa: E402
from matcher.validate import parse_model_output, validate  # noqa: E402
from rag.significance import macro_f1, mcnemar_exact, paired_bootstrap_diff  # noqa: E402

PROVIDERS = {"none": NoKnowledge, "bm25": RagKnowledge, "gated": GatedKnowledge}


def replay(run_dir, arm, cases, providers):
    prov = providers[arm.removesuffix("-repeat")]
    out, mismatched = {}, 0
    for p in map(json.loads, (Path(run_dir) / "predictions.jsonl").read_text().splitlines()):
        c = cases[p["case_id"]]
        req = Requirement(**next(r for r in c["job"]["requirements"] if r["req_id"] == p["req_id"]))
        refs = prov.lookup(req, k=3)
        mismatched += [r.source_id for r in refs] != p["rag_refs"]
        res = validate(parse_model_output(p["raw"]), CV(**c["cv"]), req, refs)
        out[(p["case_id"], p["req_id"])] = {"gold": p["gold_decision"], "decision": res.decision,
                                             "saved": p["decision"], "review": res.needs_human_review}
    return out, mismatched


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default="rag_opt/results/e2e")
    ap.add_argument("--label", default="current validator")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    cases = {c["case_id"]: c for c in map(json.loads, (ROOT / "benchmark/data/val.jsonl").read_text().splitlines())}
    providers = {k: v() for k, v in PROVIDERS.items()}
    runs = {}
    for d in sorted(Path(a.root).iterdir()):
        if (d / "predictions.jsonl").exists() and "__" in d.name:
            model, arm = d.name.split("__", 1)
            if arm.removesuffix("-repeat") in providers:
                runs.setdefault(model, {})[arm] = replay(d, arm, cases, providers)
    L = [f"# Validator replay of the E2E arms ({a.label}; saved LIVE raw outputs, no model call)", ""]
    res = {}
    for model, arms in runs.items():
        keys = sorted(set.intersection(*[set(r) for r, _ in arms.values()]))
        L += [f"## {model}", "", "| arm | n | macro-F1 | false-MET | review rate | decisions changed vs saved | refs rebuilt != saved |",
              "|---|---|---|---|---|---|---|"]
        res[model] = {"runs": {}, "paired": {}}
        for arm, (r, mism) in arms.items():
            gold = [r[k]["gold"] for k in keys]
            pred = [r[k]["decision"] for k in keys]
            neg = [k for k in keys if r[k]["gold"] != "MET"]
            row = {"n": len(keys), "macro_f1": round(macro_f1(gold, pred), 4),
                   "false_met": round(sum(r[k]["decision"] == "MET" for k in neg) / len(neg), 4),
                   "review_rate": round(sum(r[k]["review"] for k in keys) / len(keys), 4),
                   "changed_vs_saved": sum(r[k]["decision"] != r[k]["saved"] for k in keys), "refs_mismatch": mism}
            res[model]["runs"][arm] = row
            L.append(f"| {arm} | {row['n']} | {row['macro_f1']:.3f} | {row['false_met']:.3f} | {row['review_rate']:.3f} | "
                     f"{row['changed_vs_saved']} | {mism} |")
        L += ["", "| comparison | Δ macro-F1 | 95% CI | base-only / cand-only correct | McNemar p |", "|---|---|---|---|---|"]
        pairs = [(c, "none") for c in arms if c != "none" and "none" in arms]
        if "gated" in arms and "bm25" in arms:
            pairs.append(("gated", "bm25"))
        for cand, base in pairs:
            b, c = arms[base][0], arms[cand][0]
            gold = [b[k]["gold"] for k in keys]
            bd, cd = [b[k]["decision"] for k in keys], [c[k]["decision"] for k in keys]
            x, y, p = mcnemar_exact([u == g for u, g in zip(bd, gold)], [u == g for u, g in zip(cd, gold)])
            d, (lo, hi) = paired_bootstrap_diff(gold, bd, cd)
            res[model]["paired"][f"{cand} vs {base}"] = {"delta": round(d, 4), "ci95": [round(lo, 4), round(hi, 4)],
                                                         "base_only": x, "cand_only": y, "mcnemar_p": round(p, 4)}
            L.append(f"| {cand} vs {base} | {d:+.3f} | [{lo:+.3f}, {hi:+.3f}] | {x} / {y} | {p:.3f} |")
        L.append("")
    md = "\n".join(L)
    if a.out:
        Path(f"{a.out}.md").write_text(md + "\n")
        Path(f"{a.out}.json").write_text(json.dumps(res, indent=1) + "\n")
    print(md)
    return res


if __name__ == "__main__":
    main()
