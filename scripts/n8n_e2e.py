r"""End-to-end runs of the n8n workflow "HireSignal v1" through its webhook (T05 Part B), against a running stack
(scripts/start_stack.ps1 + scripts/start_n8n.ps1).

For each run: POST multipart (cv file + job_text) to the webhook, save the final JSON, then read the execution from
n8n's SQLite (read-only): status, per-node timings (runData startTime / executionTime), and an identity search:
every value of private/<cv_id>.json is searched in the execution data (plain text and decoded base64 strings).

Usage: .venv\Scripts\python scripts\n8n_e2e.py --out eval\results\<date>_n8n_e2e [--runs P15,P35,kaggle]
T10: a run "scan:<file in data/raw/scans>:<pair>" sends that phone photo / scan as the pair's CV, e.g.
     --runs scan:K01_photo.jpg:P15 --cards
"""
import argparse
import base64
import binascii
import csv
import json
import re
import sqlite3
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
WEBHOOK = "http://127.0.0.1:5678/webhook/hiresignal"


def token_header() -> dict:
    """T13: the webhook's shared secret (X-HireSignal-Token = WEBHOOK_TOKEN from .env); never printed."""
    import os
    import sys
    sys.path.insert(0, str(ROOT))
    import services.config  # noqa: F401  (loads .env)
    tok = os.environ.get("WEBHOOK_TOKEN")
    return {"X-HireSignal-Token": tok} if tok else {}
DB = ROOT / ".n8n" / "database.sqlite"


def unflatten(raw):
    """n8n stores execution data in 'flatted' form: a list whose strings inside containers are indexes."""
    arr, memo = json.loads(raw), {}

    def rev(i):
        if i in memo:
            return memo[i]
        v = arr[i]
        if isinstance(v, dict):
            out = memo[i] = {}
            out.update({k: rev(int(x)) if isinstance(x, str) else x for k, x in v.items()})
        elif isinstance(v, list):
            out = memo[i] = []
            out.extend(rev(int(x)) if isinstance(x, str) else x for x in v)
        else:
            out = memo[i] = v
        return out
    return rev(0)


def execution(exec_id):
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    status, started, stopped = con.execute(
        "select status, startedAt, stoppedAt from execution_entity where id=?", (exec_id,)).fetchone()
    raw = con.execute("select data from execution_data where executionId=?", (exec_id,)).fetchone()[0]
    con.close()
    return status, started, stopped, raw


def decoded_strings(raw):
    """Base64 strings found in the execution data, decoded (in case binary data were stored inline)."""
    out = []
    for m in re.finditer(r'"([A-Za-z0-9+/]{40,}={0,2})"', raw):
        try:
            out.append(base64.b64decode(m.group(1), validate=True).decode("utf-8", "ignore"))
        except (binascii.Error, ValueError):
            pass
    return out


def identity_values(cv_id):
    path = ROOT / "private" / f"{cv_id}.json"
    ident = json.loads(path.read_text(encoding="utf-8"))
    vals = ([ident["name"]] if ident.get("name") else []) + ident["emails"] + ident["phones"] + ident["urls"]
    vals += ident["addresses"] + [p["value"] for p in ident["personal"]]
    if ident.get("name"):
        vals += [w for w in re.split(r"\s+", ident["name"]) if len(w) >= 3]
    return sorted({v for v in vals if v.strip()})


def runs_from(names):
    pairs = {p["pair_id"]: p for p in csv.DictReader(open(ROOT / "data/labels/pairs.csv", encoding="utf-8"))}
    for p in csv.DictReader(open(ROOT / "data/labels/pairs_extra.csv", encoding="utf-8")):  # T08: 12 targeted pairs
        pairs[p["pair_id"]] = p | {"selection_stratum": p["selection"]}
    for name in names:
        if name in pairs:
            p = pairs[name]
            yield name, ROOT / "data/processed/cvs" / f"{p['cv_id']}.txt", ROOT / f"data/processed/jobs/{p['job']}.txt", \
                {"pair": name, "job": p["job"], "stratum_in_pairs_csv": p["selection_stratum"]}
        elif name.startswith("file:"):  # T13: any CV file of the repo as the pair's CV ("file:<repo path>:<pair>")
            _, file, pair = name.rsplit(":", 2) if name.count(":") > 2 else name.split(":")
            p = pairs[pair]
            yield f"{pair}_{Path(file).stem}", ROOT / file, ROOT / f"data/processed/jobs/{p['job']}.txt", \
                {"pair": pair, "job": p["job"], "cv_file": file}
        elif name.startswith("scan:"):  # T10: a phone photo or scan of the pair's CV (data/raw/scans/PHOTO_MAPPING.csv)
            _, file, pair = name.split(":")
            p = pairs[pair]
            yield f"{pair}_{Path(file).stem}", ROOT / "data/raw/scans" / file, ROOT / f"data/processed/jobs/{p['job']}.txt", \
                {"pair": pair, "job": p["job"], "cv_file": f"data/raw/scans/{file}"}
        elif name == "kaggle":
            pdf = sorted((ROOT / "data/raw/kaggle_resume/data/data/INFORMATION-TECHNOLOGY").glob("*.pdf"))[0]
            yield name, pdf, ROOT / "data/processed/jobs/J4.txt", {"pair": None, "job": "J4", "kaggle_pdf": pdf.name}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--runs", default="P15,P35,kaggle")
    ap.add_argument("--cards", action="store_true",
                    help="T08b: send the recruiter-confirmed card data/processed/jobs/<job>_requirements.json")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    summary = []
    for name, cv, job, meta in runs_from(a.runs.split(",")):
        mime = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}.get(
            cv.suffix.lower(), "text/plain")
        t = time.perf_counter()
        data = {"job_text": job.read_text(encoding="utf-8")}
        if a.cards:
            data["requirements"] = (job.parent / f"{job.stem}_requirements.json").read_text(encoding="utf-8")
            meta["requirements"] = f"data/processed/jobs/{job.stem}_requirements.json (confirmed card)"
        r = httpx.post(WEBHOOK, files={"cv": (f"cv{cv.suffix}", cv.read_bytes(), mime)}, data=data, timeout=1800,
                       headers=token_header())
        total = round(time.perf_counter() - t, 2)
        body = r.json()  # raises if the reply is not JSON
        (out / f"{name}_result.json").write_text(json.dumps(body, indent=1, ensure_ascii=False), encoding="utf-8")
        exec_id = body.get("execution_id")
        for _ in range(60):  # Respond to Webhook answers before n8n has saved the finished execution
            status, started, stopped, raw = execution(exec_id)
            if stopped and status not in ("new", "running"):
                break
            time.sleep(1)
        data = unflatten(raw)
        nodes = {n: [{"start": run.get("startTime"), "ms": run.get("executionTime"), "status": run.get("executionStatus")}
                     for run in runs] for n, runs in data["resultData"]["runData"].items()}
        vals = identity_values(body["cv_id"])
        texts = [raw] + decoded_strings(raw)
        found = [v for v in vals if any(v in s for s in texts)]
        stored_binaries = sorted(p.name for p in (ROOT / ".n8n/storage/workflows").rglob(f"executions/{exec_id}/binary_data/*")
                                 if not p.name.endswith(".metadata"))
        checks = {"http_status": r.status_code, "valid_json": True, "execution_status": status,
                  "identity_values_in_private_file": len(vals), "identity_values_found_in_execution_data": len(found),
                  "raw_cv_text_in_execution_data": False,
                  "all_match_lora_scale_1": all(q["lora_scale"] == 1 for q in body["requirements"]),
                  "quotes_verified_positions": sum(len(q["quotes"]) for q in body["requirements"]),
                  "uploaded_file_kept_by_n8n_binary_store": len(stored_binaries)}
        # raw text check: the Reader's private copy must not appear in the execution data (only the anonymised text may)
        reader = json.loads((ROOT / "private" / f"{body['cv_id']}.reader.json").read_text(encoding="utf-8"))
        lines = [ln for ln in reader["text"].splitlines() if len(ln) >= 25]
        anon = next(iter(data["resultData"]["runData"]["HTTP /profile"]))["data"]["main"][0][0]["json"]["anonymised_text"]
        raw_only = [ln for ln in lines if ln not in anon]  # lines the anonymiser changed (they hold identity)
        checks["raw_cv_text_in_execution_data"] = any(ln in raw for ln in raw_only)
        checks["changed_raw_lines_checked"] = len(raw_only)
        rec = {"run": name, **meta, "execution_id": exec_id, "n8n_started": started, "n8n_stopped": stopped,
               "total_wall_s": total, "outcome": body["outcome"], "score": body["score"],
               # T08 result fields (gate): rule / reasons / listed_flags; T05-T07: review_reasons / info_flags
               "rule": body.get("rule"), "reasons": body.get("reasons", body.get("review_reasons")),
               "listed_flags": body.get("listed_flags", body.get("info_flags")),
               "review_form_url": body.get("review_form_url"),
               "decisions": {q["req_id"]: [q["kind"], q["decision"]] for q in body["requirements"]},
               "station_timings_s": body["timings_s"], "reader": body.get("reader"), "node_timings": nodes,
               "checks": checks}
        (out / f"{name}_execution.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
        summary.append(rec)
        print(f"{name}: exec {exec_id} {status} {total}s outcome={body['outcome']} score={body['score']} "
              f"identity_found={len(found)}/{len(vals)} lora1={checks['all_match_lora_scale_1']}", flush=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
