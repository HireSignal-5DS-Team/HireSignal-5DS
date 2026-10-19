r"""T13 A4: scan everything the app writes for identity values (names, e-mails, phones, URLs, addresses).

Identity values = every value in private/cv-*.json (the identity files the Profile stores apart), at least 5
characters. They are searched (case-insensitive) in:
  - the n8n execution data (.n8n/database.sqlite, read-only; the 'flatted' JSON as stored + decoded base64 strings),
  - tools/*.log*, eval/logs/, eval/outbox/ (the letters), eval/results/**/*.json|csv|md|log (results and reports).
Prints counts only: identity values are never printed. Writes <out>/privacy_scan.json (counts and file names).

Usage: .venv\Scripts\python scripts\scan_privacy.py --out eval\results\2026-10-19_security
"""
import argparse
import base64
import binascii
import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def identity_values() -> list[str]:
    vals = set()
    for p in (ROOT / "private").glob("cv-*.json"):
        if p.name.endswith(".reader.json"):
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        # only the identity fields (services/profile/contracts.Identity): not cv_id / schema_version
        for key in ("name", "emails", "phones", "urls", "addresses"):
            for x in d.get(key) if isinstance(d.get(key), list) else [d.get(key)]:
                if isinstance(x, str) and len(x.strip()) >= 5:
                    vals.add(x.strip().lower())
        for item in d.get("personal") or []:
            v = (item or {}).get("value") if isinstance(item, dict) else None
            if isinstance(v, str) and len(v.strip()) >= 5:
                vals.add(v.strip().lower())
    return sorted(vals)


def decoded(raw: str) -> list[str]:
    out = []
    for m in re.finditer(r"[A-Za-z0-9+/]{40,}={0,2}", raw):
        try:
            out.append(base64.b64decode(m.group(0), validate=True).decode("utf-8", "ignore"))
        except (binascii.Error, ValueError):
            pass
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    vals = identity_values()
    hits = {}
    # n8n execution data
    con = sqlite3.connect(f"file:{ROOT / '.n8n' / 'database.sqlite'}?mode=ro", uri=True)
    n_exec = 0
    for exec_id, data in con.execute("select executionId, data from execution_data"):
        n_exec += 1
        texts = [data.lower()] + [t.lower() for t in decoded(data)]
        found = sum(any(v in t for t in texts) for v in vals)
        if found:
            hits[f"n8n execution {exec_id}"] = found
    # files
    files = [p for pat in ("tools/*.log*", "eval/logs/**/*", "eval/outbox/**/*", "eval/results/**/*.json",
                           "eval/results/**/*.csv", "eval/results/**/*.md", "eval/results/**/*.log", "docs/*.md",
                           "tasks/*.md") for p in ROOT.glob(pat) if p.is_file()]
    for p in files:
        try:
            t = p.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            continue
        found = sum(v in t for v in vals)
        if found:
            hits[str(p.relative_to(ROOT))] = found
    res = {"identity_files": len(list((ROOT / "private").glob("cv-*.json"))), "identity_values": len(vals),
           "n8n_executions_scanned": n_exec, "files_scanned": len(files), "places_with_identity_values": hits}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "privacy_scan.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print({k: v for k, v in res.items() if k != "places_with_identity_values"}, "hits:", len(hits))
    for k, v in sorted(hits.items())[:40]:
        print(f"  {k}: {v} value(s)")


if __name__ == "__main__":
    main()
