r"""T11 Part B: counterfactual swap test on the 52 gold pairs (variants from scripts/make_counterfactuals.py).

Two settings, each compared with its own base CV:
  prod  production: Reader -> anonymiser (rules, as /profile) -> Bias Auditor leakage check -> Matcher input
  raw   ablation: Reader text, NO anonymiser and no leakage check -> Matcher input
For each (pair, variant, setting): if the Matcher input is byte-identical to the base input of that setting, the
decisions are the base decisions (same input, temperature 0, single llama-server slot; checked with --determinism).
Otherwise the confirmed card's requirements go through the station API: /rag/search (V6) -> /match -> /judge, and
the T08b gate (eval_rag_matcher.GATE, no pair flags: profile flags are info only) gives the outcome. The Profile
parse (LLM) is not run: the Matcher never sees it and its flags are info only.
Rows are cached in <out>/<setting>/<pair>/<variant>.json; a rerun resumes.
--subset N: a fixed random subset of N pairs (half dev, half test, random.Random(11)), the same for every variant
(used for the raw ablation: ~21 s per chain run). The pairs are written to <out>/<setting>/subset.json.

Usage: .venv\Scripts\python scripts\eval_bias.py --out eval\results\2026-10-18_bias --setting prod
       [--families name-gender,origin] [--determinism 5] [--report]
"""
import argparse
import collections
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from eval_rag_matcher import GATE  # noqa: E402
from services.bias.auditor import leakage_check  # noqa: E402
from services.job.injection import sanitise_injection  # noqa: E402
from services.matcher.validate import evidence_years  # noqa: E402
from services.outcome.gate import decide  # noqa: E402
from services.profile.anonymise import anonymise_cv  # noqa: E402
from services.reader import read_cv  # noqa: E402

CF = ROOT / "data/processed/counterfactuals"
FAMILY_ORDER = ["name-gender", "origin", "age", "family", "language"]


def matcher_input(path: Path, setting: str) -> str:
    r = read_cv(path.read_bytes(), "cv.txt")
    if setting == "raw":
        return r.text
    text = leakage_check(anonymise_cv(r.text, cv_id="cv-00000000", sections=r.sections).text)[0]
    return sanitise_injection(text)[0]  # T14: same guard as /profile and /bias (services/api.py matcher_guard)


def card(job: str) -> list[dict]:
    reqs = json.loads((ROOT / f"data/processed/jobs/{job}_requirements.json").read_text(encoding="utf-8"))["requirements"]
    return [{k: q.get(k) for k in ("req_id", "text", "kind", "category", "skill_terms", "min_years")} for q in reqs]


def run_chain(c: httpx.Client, cv_text: str, reqs: list[dict]) -> dict:
    t = time.perf_counter()
    results = []
    for req in reqs:
        rag = c.post("/rag/search", json={"requirement": req, "cv_text": cv_text}).raise_for_status().json()
        m = c.post("/match", json={"cv_text": cv_text, "requirement": req, "knowledge_refs": rag["knowledge_refs"],
                                   "knowledge": rag["retriever"]}).raise_for_status().json()
        m = c.post("/judge", json={"cv_text": cv_text, "requirement": req, "match": m}).raise_for_status().json()
        results.append((req, m))
    gate_in = [{"req_id": m["req_id"], "kind": q["kind"], "decision": m["decision"], "review_reasons": m["review_reasons"],
                "info_flags": m["info_flags"], "category": q["category"], "min_years": q["min_years"],
                "confidence": (m.get("confidence") or {}).get("normalized"), "judge": m.get("judge"),
                "evidence_years": evidence_years([x["quote"] for x in m["evidence"]])
                if q["min_years"] and m["evidence"] else None} for q, m in results]
    g = decide(gate_in, [], [], **GATE)
    return {"decisions": {m["req_id"]: m["decision"] for _, m in results},
            "kinds": {q["req_id"]: q["kind"] for q in reqs}, "outcome": g.outcome, "score": g.score, "rule": g.rule,
            "quotes": {m["req_id"]: [x["quote"] for x in m["evidence"]] for _, m in results},
            "elapsed_s": round(time.perf_counter() - t, 2)}


def subset(manifest: dict, n: int) -> list[str]:
    import random
    rng = random.Random(11)
    out = []
    for sp in ("dev", "test"):
        ids = sorted(p for p, i in manifest["pairs"].items() if i["split"] == sp)
        out += sorted(rng.sample(ids, n // 2))
    return out


def run(out: Path, setting: str, families: list[str], api: str, n_subset: int = 0, pairs: list[str] | None = None):
    manifest = json.loads((CF / "manifest.json").read_text(encoding="utf-8"))
    if n_subset or pairs:
        keep = pairs or subset(manifest, n_subset)
        (out / setting).mkdir(parents=True, exist_ok=True)
        (out / setting / "subset.json").write_text(json.dumps(
            {"seed": 11, "pairs": keep, "families": families,
             "how": "--pairs: given list" if pairs else f"--subset {n_subset}: random.Random(11), half dev / half test"}),
            encoding="utf-8")
        manifest["pairs"] = {p: i for p, i in manifest["pairs"].items() if p in keep}
    c = httpx.Client(base_url=api, timeout=900)
    order = [(pid, vid, v["family"]) for fam in families for pid, info in manifest["pairs"].items()
             for vid, v in info["variants"].items() if v["family"] == fam]
    bases = {}
    for pid, info in manifest["pairs"].items():  # bases first (every family is compared with them)
        p = out / setting / pid / "base.json"
        text = matcher_input(CF / pid / "base.txt", setting)
        bases[pid] = text
        if not p.exists():
            res = run_chain(c, text, card(info["job"])) | {"identical_to_base": True, "ran": True}
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
            print(setting, pid, "base", res["outcome"], res["elapsed_s"], flush=True)
    for pid, vid, fam in order:
        p = out / setting / pid / f"{vid}.json"
        if p.exists():
            continue
        text = matcher_input(CF / pid / f"{vid}.txt", setting)
        if text == bases[pid]:
            base = json.loads((out / setting / pid / "base.json").read_text(encoding="utf-8"))
            res = {k: base[k] for k in ("decisions", "kinds", "outcome", "score", "rule")} | {
                "identical_to_base": True, "ran": False, "elapsed_s": 0}
        else:
            res = run_chain(c, text, card(manifest["pairs"][pid]["job"])) | {"identical_to_base": False, "ran": True}
        p.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        print(setting, pid, vid, res["outcome"], "identical" if res["identical_to_base"] else "ran", res["elapsed_s"],
              flush=True)


def determinism(out: Path, n: int, api: str):
    """Run the prod base of the first n pairs again: decisions must be equal to the cached base run."""
    manifest = json.loads((CF / "manifest.json").read_text(encoding="utf-8"))
    c = httpx.Client(base_url=api, timeout=900)
    same = []
    for pid in list(manifest["pairs"])[:n]:
        base = json.loads((out / "prod" / pid / "base.json").read_text(encoding="utf-8"))
        again = run_chain(c, matcher_input(CF / pid / "base.txt", "prod"), card(manifest["pairs"][pid]["job"]))
        same.append({"pair": pid, "decisions_equal": again["decisions"] == base["decisions"],
                     "quotes_equal": again["quotes"] == base["quotes"], "outcome_equal": again["outcome"] == base["outcome"]})
        print(same[-1], flush=True)
    (out / "determinism.json").write_text(json.dumps(same, indent=1), encoding="utf-8")


def report(out: Path):
    manifest = json.loads((CF / "manifest.json").read_text(encoding="utf-8"))
    summary = {}
    for setting in ("prod", "raw"):
        if not (out / setting).exists():
            continue
        rows = []
        sub = out / setting / "subset.json"
        keep = set(json.loads(sub.read_text(encoding="utf-8"))["pairs"]) if sub.exists() else set(manifest["pairs"])
        for pid, info in manifest["pairs"].items():
            if pid not in keep:
                continue
            bp = out / setting / pid / "base.json"
            if not bp.exists():
                continue
            base = json.loads(bp.read_text(encoding="utf-8"))
            for vid, v in info["variants"].items():
                p = out / setting / pid / f"{vid}.json"
                if not p.exists():
                    continue
                r = json.loads(p.read_text(encoding="utf-8"))
                flips = [k for k, d in base["decisions"].items() if r["decisions"].get(k) != d]
                rows.append({"pair": pid, "split": info["split"], "variant": vid, "family": v["family"], "group": v["group"],
                             "identical": r["identical_to_base"], "req_total": len(base["decisions"]),
                             "req_flips": flips, "must_flips": [k for k in flips if base["kinds"][k] == "must"],
                             "outcome_base": base["outcome"], "outcome": r["outcome"],
                             "score_delta": r["score"] - base["score"]})
        res = {}
        for sp in ("dev", "test", "all"):
            sel = [r for r in rows if sp == "all" or r["split"] == sp]
            fam = {}
            for f in FAMILY_ORDER:
                fr = [r for r in sel if r["family"] == f]
                if not fr:
                    continue
                fam[f] = {"variants_run": len(fr), "matcher_input_identical": sum(r["identical"] for r in fr),
                          "req_flip_rate": round(sum(len(r["req_flips"]) for r in fr) / max(1, sum(r["req_total"] for r in fr)), 4),
                          "outcome_flip_rate": round(sum(r["outcome"] != r["outcome_base"] for r in fr) / len(fr), 4),
                          "outcome_flips": sum(r["outcome"] != r["outcome_base"] for r in fr),
                          "mean_score_change": round(sum(r["score_delta"] for r in fr) / len(fr), 2),
                          "mean_abs_score_change": round(sum(abs(r["score_delta"]) for r in fr) / len(fr), 2)}
            groups = collections.defaultdict(list)
            for r in sel:
                groups[(r["family"], r["group"])].append(r)
            fairness = {f"{f}:{g}": {"n": len(rs), "invite": sum(r["outcome"] == "invite" for r in rs),
                                     "not_reject": sum(r["outcome"] != "reject" for r in rs),
                                     "reject": sum(r["outcome"] == "reject" for r in rs)}
                        for (f, g), rs in sorted(groups.items())}
            base_rows = {r["pair"]: r["outcome_base"] for r in sel}
            fairness["base"] = {"n": len(base_rows), "invite": sum(o == "invite" for o in base_rows.values()),
                                "not_reject": sum(o != "reject" for o in base_rows.values()),
                                "reject": sum(o == "reject" for o in base_rows.values())}
            res[sp] = {"families": fam, "fairness": fairness}
        res["flip_examples"] = [r for r in rows if r["req_flips"] or r["outcome"] != r["outcome_base"]]
        summary[setting] = res
    (out / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    for setting, res in summary.items():
        for sp in ("dev", "test"):
            print(f"== {setting} {sp}")
            for f, v in res[sp]["families"].items():
                print(f"   {f:12s} {v}")
        print(f"   flip examples: {len(res['flip_examples'])}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--setting", choices=("prod", "raw"))
    ap.add_argument("--families", default=",".join(FAMILY_ORDER))
    ap.add_argument("--api", default="http://127.0.0.1:8010")
    ap.add_argument("--determinism", type=int, default=0)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--subset", type=int, default=0)
    ap.add_argument("--pairs", help="comma-separated pair ids (a fixed subset)")
    a = ap.parse_args()
    out = Path(a.out)
    if a.setting:
        run(out, a.setting, a.families.split(","), a.api, a.subset, a.pairs.split(",") if a.pairs else None)
    if a.determinism:
        determinism(out, a.determinism, a.api)
    if a.report:
        report(out)


if __name__ == "__main__":
    main()
