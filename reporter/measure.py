"""Measure the SLM report writer on real model outputs (val only).

    flock /home/user/hs_queue.lock python -m reporter.measure --n 20 --out reporter/results/val_replay

Input: pipeline outputs rebuilt from the saved LIVE LoRA Matcher outputs (reporter/replay.py, val). The prompt and the
validator were developed on val-000..val-004 (DEV_CASES); those cases are excluded here.
Output folder: metrics.json (latency p50/p95, peak RSS, acceptance/fallback shares, audit, injection), sections.jsonl,
examples.md, and the full reports (JSON/HTML/MD) of every measured case.

Audit (independent of the writer's own validator): for every section in the final report written by the SLM,
(a) each quoted string occurs verbatim in the CV text from benchmark/data/val.jsonl, (b) each number occurs in the
facts, (c) no hiring verdict word, (d) the decision word equals the pipeline decision, and (e) the section passes the
validator again. Injection: each accepted SLM text is corrupted 5 ways (new skill, new number, new employer, verdict,
flipped decision); the validator must reject every variant.
"""
import argparse
import json
import re
import resource
import statistics
import time
from pathlib import Path

from .build import facts_for_requirement, facts_for_summary
from .render import to_html, to_markdown
from .replay import RUN, pipeline_output, val_cases
from .slm import LlamaCppSLM
from .slm_validate import NUMBER, VERDICT, validate
from .writer import write

DEV_CASES = {f"val-{i:03d}" for i in range(5)}
FLIP = {"MET": "MISSING", "MISSING": "MET", "UNCERTAIN": "MET"}


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, max(0, round(q * (len(xs) - 1))))] if xs else None


def injections(text, kind, decision):
    flipped = text.replace(decision, FLIP[decision], 1) if kind == "note" else text.replace("MET", "MISSING", 1)
    return {"new_skill": text.rstrip(".") + ", and Kubernetes.",
            "new_number": text.rstrip(".") + ", over 17 years.",
            "new_employer": text.rstrip(".") + " at Deloitte.",
            "verdict": text.rstrip(".") + "; we recommend hiring.",
            "flipped_decision": flipped if flipped != text else text + " UNCERTAIN."}


def audit(text, facts, kind, cv_text, decision):
    errs = []
    for q in re.findall(r"\"([^\"]+)\"", text):
        if q.strip().rstrip(".") not in cv_text and q.strip() not in json.dumps(facts, ensure_ascii=False):
            errs.append(f"quote_not_in_cv:{q[:40]}")
    nums = set(NUMBER.findall(json.dumps(facts, ensure_ascii=False)))
    errs += [f"number:{n}" for n in NUMBER.findall(re.sub(r"\"[^\"]+\"", " ", text)) if n not in nums]
    if VERDICT.search(re.sub(r"\"[^\"]+\"", " ", text)):
        errs.append("verdict")
    if kind == "note" and set(re.findall(r"\b(MET|MISSING|UNCERTAIN)\b", text)) - {decision}:
        errs.append("decision")
    if validate(json.dumps({kind: text}), facts, kind)[0] is None:
        errs.append("revalidation")
    return errs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--out", default="reporter/results/val_replay")
    a = ap.parse_args(argv)
    cases = val_cases()
    saved = {json.loads(line)["case_id"] for line in (RUN / "predictions.jsonl").read_text().splitlines()}
    ids = [c for c in sorted(cases) if c in saved and c not in DEV_CASES][: a.n]
    out_dir = Path(a.out)
    (out_dir / "reports").mkdir(parents=True, exist_ok=True)
    rss0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    slm = LlamaCppSLM()
    rss_loaded = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    rows, report_lat, audit_fail, inj = [], [], [], {"total": 0, "rejected": 0, "by_kind": {}}
    for cid in ids:
        out, title = pipeline_output(cid, cases=cases)
        t0 = time.perf_counter()
        rep = write(out, slm=slm, job_title=title)
        report_lat.append(time.perf_counter() - t0)
        stem = out_dir / "reports" / cid
        stem.with_suffix(".report.json").write_text(json.dumps(rep.model_dump(mode="json"), indent=2,
                                                               ensure_ascii=False) + "\n")
        stem.with_suffix(".html").write_text(to_html(rep))
        stem.with_suffix(".md").write_text(to_markdown(rep))
        cv_text = cases[cid]["cv"]["text"]
        secs = [("summary", None, rep.executive_summary, facts_for_summary(out), None)] + [
            ("note", r.req_id, r.plain_note, facts_for_requirement(row), r.decision)
            for r, row in zip(rep.requirements, out["requirements"])]
        for kind, rid, t, facts, dec in secs:
            row = {"case_id": cid, "req_id": rid, "kind": kind, "decision": dec, "writer": t.writer,
                   "attempts": t.attempts, "latency_s": t.latency_s, "text": t.text, "rejections": t.rejections,
                   "rejected_outputs": t.rejected_outputs}
            if t.writer == "slm":
                errs = audit(t.text, facts, kind, cv_text, dec)
                row["audit"] = errs
                if errs:
                    audit_fail.append((cid, rid, errs))
                ftxt = json.dumps(facts, ensure_ascii=False)
                for k, bad in injections(t.text, kind, dec or "MET").items():
                    if any(w in ftxt for w in ("Kubernetes", "Deloitte", "17")) and k in ("new_skill", "new_employer",
                                                                                       "new_number"):
                        continue  # the injected term is a fact here: not a hallucination
                    ok = validate(json.dumps({kind: bad}), facts, kind)[0] is None
                    inj["total"] += 1
                    inj["rejected"] += ok
                    d = inj["by_kind"].setdefault(k, [0, 0])
                    d[0] += ok
                    d[1] += 1
            rows.append(row)
        print(cid, f"{report_lat[-1]:.1f}s", rep.provenance.sections_slm, "/", rep.provenance.sections_total, flush=True)
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    n = len(rows)

    def share(pred):
        return round(sum(map(pred, rows)) / n, 3)

    by_kind = {}
    for k in ("summary", "note"):
        rk = [r for r in rows if r["kind"] == k]
        by_kind[k] = {"n": len(rk), "slm_first_try": sum(r["writer"] == "slm" and r["attempts"] == 1 for r in rk),
                      "slm_after_retry": sum(r["writer"] == "slm" and r["attempts"] == 2 for r in rk),
                      "fallback": sum(r["writer"] == "deterministic_fallback" for r in rk),
                      "latency_p50_s": pct([r["latency_s"] for r in rk], 0.5),
                      "latency_p95_s": pct([r["latency_s"] for r in rk], 0.95)}
    codes = {}
    for r in rows:
        for rej in r["rejections"]:
            for c in {x.split(":")[0] for x in rej.split("; ")}:
                codes[c] = codes.get(c, 0) + 1
    metrics = {
        "label": "LIVE SLM run (Qwen3-0.6B Q8_0, llama.cpp CPU) on pipeline outputs replayed from LIVE LoRA Matcher "
                 "outputs (val)",
        "matcher_run": str(RUN.relative_to(RUN.parents[3])), "cases": ids, "dev_cases_excluded": sorted(DEV_CASES),
        "slm": slm.info(), "sections": n, "reports": len(ids),
        "accepted_share": share(lambda r: r["writer"] == "slm"),
        "accepted_first_try_share": share(lambda r: r["writer"] == "slm" and r["attempts"] == 1),
        "fallback_share": share(lambda r: r["writer"] == "deterministic_fallback"),
        "by_kind": by_kind, "rejection_codes": dict(sorted(codes.items(), key=lambda x: -x[1])),
        "section_latency_p50_s": pct([r["latency_s"] for r in rows], 0.5),
        "section_latency_p95_s": pct([r["latency_s"] for r in rows], 0.95),
        "report_latency_p50_s": round(pct(report_lat, 0.5), 2), "report_latency_p95_s": round(pct(report_lat, 0.95), 2),
        "report_latency_mean_s": round(statistics.mean(report_lat), 2),
        "peak_rss_mb": {"process_start": round(rss0), "after_model_load": round(rss_loaded), "peak": round(peak)},
        "audit_unsupported_claims_in_final_reports": len(audit_fail), "audit_failures": audit_fail,
        "injection": {**inj, "rejection_rate": round(inj["rejected"] / inj["total"], 3) if inj["total"] else None},
    }
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n")
    (out_dir / "sections.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    ex = ["# Examples (val, LIVE SLM on replayed LIVE LoRA Matcher outputs)", ""]
    for title, pred in [("Accepted on the first try", lambda r: r["writer"] == "slm" and r["attempts"] == 1),
                        ("Accepted after the corrective retry", lambda r: r["writer"] == "slm" and r["attempts"] == 2),
                        ("Fallen back to the deterministic text", lambda r: r["writer"] == "deterministic_fallback")]:
        ex += [f"## {title}", ""]
        for r in [r for r in rows if pred(r)][:6]:
            ex += [f"- `{r['case_id']}` {r['req_id'] or 'summary'} ({r['decision'] or ''}): {r['text']}"]
            ex += [f"  - rejected attempt: `{o}` — {why}" for o, why in zip(r["rejected_outputs"], r["rejections"])]
        ex.append("")
    (out_dir / "examples.md").write_text("\n".join(ex))
    print(json.dumps({k: v for k, v in metrics.items() if k not in ("slm", "cases", "audit_failures")}, indent=1))


if __name__ == "__main__":
    main()
