r"""T12: Report Writer evaluation on the decision records (scripts/make_report_records.py). Choose on dev, test once.

Setups: template | 4b-v0 | 4b-v1 (Qwen3-4B plain on llama-server :8090, LoRA scale 0) | 0.6b-v1 (Qwen3-0.6B on a
temporary llama-server, --base-url / --model). Measures per setup: fact-check pass on the first try and after the retry,
template-fallback rate, checker errors on the first try ("invented facts"), must-haves covered with the right decision
on the first try, words (summary + letter), latency per report, peak VRAM (nvidia-smi every 0.2 s).
Outputs: <out>/<setup>/<split>/<id>.json (record id, report, errors) and <out>/summary.json.

Usage: .venv\Scripts\python scripts\eval_report_writer.py --out eval\results\<date>_report_writer --setup 4b-v1 --split dev
"""
import argparse
import glob
import json
import re
import statistics
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from eval_multimodal import VramPeak  # noqa: E402
from services.report.checker import check  # noqa: E402
from services.report.template import render  # noqa: E402
from services.report.writer import write_report  # noqa: E402

PROMPTS = {f"v{i}": f"prompts/report_writer/v{i}.md" for i in range(4)}


def must_covered(record, report):
    lines = {x.get("req_id"): x.get("decision") for x in (report or {}).get("requirements") or []}
    must = [r for r in record["requirements"] if r["kind"] == "must"]
    return sum(lines.get(r["req_id"]) == r["decision"] for r in must), len(must)


def first_report(out):
    return out.get("first_report")


def run(a):
    files = sorted(glob.glob(str(ROOT / f"data/processed/report_records/{a.split}/*.json")))
    d = Path(a.out) / a.setup / a.split
    d.mkdir(parents=True, exist_ok=True)
    client = httpx.Client(timeout=600)
    for f in files:
        rec = json.loads(Path(f).read_text(encoding="utf-8"))
        p = d / f"{rec['id']}.json"
        if p.exists():
            continue
        if a.setup == "template":
            import time
            t = time.perf_counter()
            rep = render(rec)
            res = {"report": rep, "source": "template", "attempts": 0, "first_errors": check(rec, rep),
                   "retry_errors": [], "latency_s": round(time.perf_counter() - t, 4), "peak_vram_mib": None}
        else:
            prompt = PROMPTS[a.setup.split("-")[1]]
            with VramPeak() as vr:
                res = write_report(rec, prompt=prompt, client=client, base_url=a.base_url, model=a.model)
            res["peak_vram_mib"] = vr.peak
        res |= {"id": rec["id"], "outcome": rec["outcome"], "synthetic_flags": rec.get("synthetic_flags", False)}
        p.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        print(a.setup, rec["id"], rec["outcome"], res["source"], res["attempts"], len(res["first_errors"]),
              res["latency_s"], flush=True)


def summarise(out: Path):
    summary = {}
    for setup_dir in sorted(p for p in out.iterdir() if p.is_dir()):
        for split_dir in sorted(p for p in setup_dir.iterdir() if p.is_dir()):
            rows = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(split_dir.glob("*.json"))]
            if not rows or split_dir.name not in ("dev", "test", "dev_human", "test_human"):
                continue  # e.g. old_checker/ (the first run, before the dev fix of the checker)
            recs = {r["id"]: json.loads(Path(ROOT / f"data/processed/report_records/{split_dir.name}/{r['id']}.json")
                                        .read_text(encoding="utf-8")) for r in rows}
            n = len(rows)
            first_pass = sum(not r["first_errors"] for r in rows)
            final_llm = sum(r["source"] == "llm" for r in rows)
            cov = [must_covered(recs[r["id"]], r["report"]) for r in rows]
            words = [len((r["report"]["recruiter_summary"] + " " + r["report"]["candidate_letter"]).split()) for r in rows]
            lat = [r["latency_s"] for r in rows]
            errs = [len(r["first_errors"]) for r in rows]
            kinds = {}
            for r in rows:
                for e in r["first_errors"]:
                    k = re.sub(r"\br\d+\b:?\s*", "", e)  # group by kind: drop the req ids
                    k = re.sub(r"\b(?:number|placeholder) \S+", lambda m: m.group(0).split()[0], k).strip()
                    kinds[k] = kinds.get(k, 0) + 1
            summary[f"{setup_dir.name}/{split_dir.name}"] = {
                "n": n, "pass_first_try": f"{first_pass}/{n}",
                "pass_after_retry_llm": f"{final_llm}/{n}" if setup_dir.name != "template" else f"{first_pass}/{n}",
                "template_fallback": f"{sum(r['source'] == 'template' for r in rows) if setup_dir.name != 'template' else 0}/{n}",
                "checker_errors_first_try_mean": round(statistics.mean(errs), 2),
                "must_covered_final": f"{sum(c for c, _ in cov)}/{sum(t for _, t in cov)}",
                "words_mean": round(statistics.mean(words), 1), "latency_s_mean": round(statistics.mean(lat), 2),
                "latency_s_max": max(lat), "peak_vram_mib": max((r.get("peak_vram_mib") or 0 for r in rows), default=None),
                "first_error_kinds": dict(sorted(kinds.items(), key=lambda x: -x[1]))}
    (out / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    for k, v in summary.items():
        print(k, {x: y for x, y in v.items() if x != "first_error_kinds"})
        print("    errors:", v["first_error_kinds"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--setup", choices=("template", "4b-v0", "4b-v1", "4b-v2", "4b-v3", "0.6b-v1", "0.6b-v2"))
    ap.add_argument("--split", default="dev", choices=("dev", "test", "dev_human", "test_human"))
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--summary", action="store_true")
    a = ap.parse_args()
    if a.setup:
        run(a)
    if a.summary:
        summarise(Path(a.out))


if __name__ == "__main__":
    main()
