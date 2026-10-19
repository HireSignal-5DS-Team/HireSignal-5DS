r"""Real smoke run of the station API (T04 Part D3), against a running stack (scripts/start_stack.ps1).

  1. one Kaggle INFORMATION-TECHNOLOGY PDF -> /reader -> /profile
  2. one Djinni CV (data/processed/cvs, the CV of the first J2 pair) -> /reader -> /profile
  3. data/processed/jobs/J2.txt -> /job
  4. /match for every requirement of that job on the Djinni CV (anonymised text)

Checks: every response validates against services/contracts.py; no identity value (private/<cv_id>.json) appears in any
/profile, /job or /match response; every quote equals cv_text[start:end]; no model_output_invalid.
Since T05 the Reader returns no raw text (it stays in private/<cv_id>.reader.json, git-ignored).

Usage: .venv\\Scripts\\python scripts\\api_smoke.py --out eval\\results\\<date>_api_smoke
"""
import argparse
import csv
import hashlib
import json
import shutil
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
import sys  # noqa: E402

sys.path.insert(0, str(ROOT))
from services.contracts import JobOut, MatchOut, ProfileOut, ReaderOut  # noqa: E402


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def identity_values(cv_id):
    ident = json.loads((ROOT / "private" / f"{cv_id}.json").read_text(encoding="utf-8"))
    vals = ([ident["name"]] if ident.get("name") else []) + ident["emails"] + ident["phones"] + ident["urls"] + ident["addresses"]
    vals += [p["value"] for p in ident["personal"]]
    if ident.get("name"):
        vals += [w for w in ident["name"].split() if len(w) >= 3]
    return [v for v in vals if v.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8010")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out, priv = Path(a.out), ROOT / "private" / "api_smoke"
    (out / "inputs").mkdir(parents=True, exist_ok=True)
    priv.mkdir(parents=True, exist_ok=True)
    c = httpx.Client(base_url=a.api, timeout=900)
    timings, checks, calls = [], [], {}

    def post(name, path, **kw):
        t = time.perf_counter()
        r = c.post(path, **kw)
        wall = round(time.perf_counter() - t, 3)
        r.raise_for_status()
        body = r.json()
        timings.append({"call": name, "endpoint": path, "wall_s": wall, "server_s": body.get("elapsed_s")})
        calls[name] = body
        return body

    pdf = sorted((ROOT / "data/raw/kaggle_resume/data/data/INFORMATION-TECHNOLOGY").glob("*.pdf"))[0]
    pair = next(p for p in csv.DictReader(open(ROOT / "data/labels/pairs.csv", encoding="utf-8")) if p["job"] == "J2")
    cv_txt = ROOT / "data/processed/cvs" / f"{pair['cv_id']}.txt"
    job_txt = ROOT / "data/processed/jobs/J2.txt"
    shutil.copy(cv_txt, out / "inputs" / cv_txt.name)
    shutil.copy(job_txt, out / "inputs" / "J2.txt")
    inputs = {"kaggle_pdf": {"path": str(pdf.relative_to(ROOT)), "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest()},
              "djinni_cv": {"path": str(cv_txt.relative_to(ROOT)), "pair": pair["pair_id"]},
              "job": {"path": str(job_txt.relative_to(ROOT))}}

    profiles = {}
    for name, path, mime in (("kaggle_pdf", pdf, "application/pdf"), ("djinni_cv", cv_txt, "text/plain")):
        rd = post(f"reader_{name}", "/reader", files={"file": (f"cv{path.suffix}", path.read_bytes(), mime)})
        ReaderOut.model_validate(rd)
        pr = post(f"profile_{name}", "/profile", json={"cv_id": rd["cv_id"]})  # T05: raw text stays in private/
        ProfileOut.model_validate(pr)
        profiles[name] = pr

    job = post("job_J2", "/job", json={"job_text": job_txt.read_text(encoding="utf-8"), "job_id": "J2"})
    JobOut.model_validate(job)

    cv_text = profiles["djinni_cv"]["anonymised_text"]
    matches = []
    for r in job["card"]["requirements"]:
        req = {k: r[k] for k in ("req_id", "text", "kind", "category", "skill_terms", "min_years")}
        m = post(f"match_{r['req_id']}", "/match", json={"cv_text": cv_text, "requirement": req,
                                                        "cv_id": profiles["djinni_cv"]["cv_id"]})
        MatchOut.model_validate(m)
        matches.append(m)

    # ------------------------------------------------------------- checks ---
    for name, pr in profiles.items():
        vals = identity_values(pr["cv_id"])
        leaked = [v for v in vals for k, body in calls.items() if v in json.dumps(body, ensure_ascii=False)]
        checks.append({"check": f"no identity of {name} in any response (reader, profile, job, match)",
                       "identity_values_found_in_private_file": len(vals), "ok": not leaked,
                       "leaked_count": len(leaked)})
    bad = [(m["req_id"], e["quote"]) for m in matches for e in m["evidence"] if cv_text[e["start"]:e["end"]] != e["quote"]]
    checks.append({"check": "every quote == cv_text[start:end]", "quotes": sum(len(m["evidence"]) for m in matches),
                   "ok": not bad})
    checks.append({"check": "no model_output_invalid in /match", "ok": not any("model_output_invalid" in m["review_reasons"] for m in matches)})
    checks.append({"check": "all responses validate against services/contracts.py", "ok": True})
    checks.append({"check": "/match lora_scale 1, /profile and /job run with scale 0 (client default)",
                   "ok": all(m["model"]["lora_scale"] == 1.0 for m in matches)})

    (out / "inputs" / "inputs.json").write_text(json.dumps(inputs, indent=1), encoding="utf-8")
    (out / "outputs.json").write_text(json.dumps(calls, indent=1, ensure_ascii=False), encoding="utf-8")
    (out / "timings.json").write_text(json.dumps(timings, indent=1), encoding="utf-8")
    (out / "checks.json").write_text(json.dumps(checks, indent=1), encoding="utf-8")
    health = c.get("/ready").json()
    (out / "config.json").write_text(json.dumps({"date": time.strftime("%Y-%m-%d %H:%M:%S"), "label": "real-GPU",
                                                  "api": a.api, "ready": health,
                                                  "llm_props": httpx.get("http://127.0.0.1:8090/props").json().get("build_info")},
                                                 indent=1), encoding="utf-8")
    rows = [f"| {t['call']} | {t['endpoint']} | {t['wall_s']} | {t['server_s']} |" for t in timings]
    print("\n".join(["| call | endpoint | wall s | server s |", "|---|---|---|---|"] + rows))
    print(json.dumps(checks, indent=1))
    print("decisions:", [(m["req_id"], m["decision"], m["review_reasons"]) for m in matches])


if __name__ == "__main__":
    main()
