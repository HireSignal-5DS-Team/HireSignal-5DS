r"""T14 Part D: secret scan of everything git would commit. Prints counts and file paths only, never a value.

Looks for: every secret value in .env (keys named *KEY* / *TOKEN* / *SECRET* / *PASS*, length >= 6), common key patterns (OpenAI / HF / GitHub /
AWS / private keys / bearer tokens), and the identity values stored in private/*.json (length >= 5, the same rule as
scripts/scan_privacy.py). The file list is `git ls-files --cached --others --exclude-standard`, i.e. exactly what
`git add -A` would stage.
Usage: .venv\Scripts\python scripts\secret_scan.py [--out eval\results\<date>_secret_scan\scan.json]
"""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "openai key": r"sk-[A-Za-z0-9_-]{20,}",
    "huggingface token": r"hf_[A-Za-z0-9]{30,}",
    "github token": r"gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}",
    "aws key": r"AKIA[0-9A-Z]{16}",
    "private key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "google api key": r"AIza[0-9A-Za-z_-]{35}",
    "bearer token": r"(?i)bearer\s+[A-Za-z0-9._-]{20,}",
}
PLACEHOLDER = re.compile(r"(?i)^(change[-_]?me|your[-_].*|<.*>|x+|none|true|false|on|off|late|info|\d+(\.\d+)?|"
                         r"https?://(127\.0\.0\.1|localhost)[^ ]*|[a-z]:\\.*|\.?/?[\w./\\-]+\.(md|gguf|json|txt))$")


def env_values() -> dict[str, str]:
    out = {}
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                v = v.strip().strip('"').strip("'")
                secret = re.search(r"KEY|TOKEN|SECRET|PASS", k.upper())
                if secret and len(v) >= 6 and not PLACEHOLDER.match(v):  # ports / model names / paths are not secrets
                    out[k.strip()] = v
    return out


def identity_values() -> set[str]:
    vals = set()
    for f in (ROOT / "private").rglob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        # T18: only identity-store files (written by /profile: name, emails, phones, urls, addresses, personal).
        # Reader texts (*.reader.json) and pipeline results kept in private/ (e.g. my_test/result.json) are not
        # identity values: their generic strings ("r2: must-have MISSING") gave false hits.
        if not (isinstance(d, dict) and "emails" in d and "name" in d and not f.name.endswith(".reader.json")):
            continue
        d = {k: v for k, v in d.items() if k in ("name", "emails", "phones", "urls", "addresses", "personal")}
        stack = [d]
        while stack:
            x = stack.pop()
            if isinstance(x, dict):
                stack += [v for k, v in x.items() if k not in ("cv_id", "schema_version", "created", "source")]
            elif isinstance(x, list):
                stack += x
            elif isinstance(x, str) and len(x.strip()) >= 5:
                vals.add(x.strip())
    return vals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    a = ap.parse_args()
    files = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT,
                           capture_output=True, check=True).stdout.decode("utf-8").split("\0")
    files = [f for f in files if f and (ROOT / f).is_file()]
    env, ident = env_values(), identity_values()
    hits = {"env value": [], "key pattern": [], "identity value": []}
    for f in files:
        try:
            text = (ROOT / f).read_bytes().decode("utf-8", errors="ignore")
        except OSError:
            continue
        for k, v in env.items():
            if v in text:
                hits["env value"].append({"file": f, "env_key": k})
        for name, pat in PATTERNS.items():
            if re.search(pat, text):
                hits["key pattern"].append({"file": f, "pattern": name})
        found = [v for v in ident if v in text]
        if found:
            hits["identity value"].append({"file": f, "values": len(found)})
    # Identity hits are explained by rule: private/ also holds older false detections and synthetic test identities.
    # A value is explained if it occurs in (a) the public dataset text we ship (Djinni / Kaggle CVs and jobs, MIT /
    # CC0, see data/processed/NOTICE_DJINNI.md), (b) a synthetic identity source made for tests, or (c) our own code
    # (reader / system messages that older versions stored). Anything else is "unexplained" and blocks the push.
    def corpus(globs):
        return "\n".join((ROOT / f).read_text(encoding="utf-8", errors="ignore") for g in globs for f in
                         [str(p.relative_to(ROOT)) for p in ROOT.glob(g) if p.is_file()])
    public = corpus(["data/processed/cvs/*.txt", "data/processed/jobs/*.txt", "rag/data/**/*.csv"])
    synthetic = corpus(["tests/**/*.py", "tests/fixtures/**/*", "data/processed/counterfactuals/manifest.json",
                        "eval/results/2026-10-19_security/synthetic_identity_cv.txt"])
    code = corpus(["services/**/*.py", "scripts/*.py"])
    found_values = {v for v in ident if any(v in (ROOT / h["file"]).read_bytes().decode("utf-8", errors="ignore")
                                            for h in hits["identity value"])}
    # (d) values a person reviewed, stored as sha256 only (never the value): config/secret_scan_reviewed.json
    reviewed_file = ROOT / "config/secret_scan_reviewed.json"
    reviewed = json.loads(reviewed_file.read_text(encoding="utf-8")) if reviewed_file.exists() else {}
    why = {"public dataset text": 0, "synthetic test identity": 0, "app text / older false detection": 0,
           "reviewed (hash list)": 0}
    unexplained = 0
    for v in sorted(found_values):
        h = hashlib.sha256(v.encode("utf-8")).hexdigest()
        if v in public:
            why["public dataset text"] += 1
        elif v in synthetic:
            why["synthetic test identity"] += 1
        elif v.lower() in code.lower() or v[:25] in code:  # a reader / system message (numbers filled in)
            why["app text / older false detection"] += 1
        elif h in reviewed:
            why["reviewed (hash list)"] += 1
        else:
            print("UNEXPLAINED sha256", h)
            unexplained += 1
            print("UNEXPLAINED identity value in", [h["file"] for h in hits["identity value"]
                                                    if v in (ROOT / h["file"]).read_text(encoding="utf-8",
                                                                                        errors="ignore")][:5])
    res = {"files_scanned": len(files), "env_values_checked": sorted(env), "identity_values_checked": len(ident),
           "hits": {k: len(v) for k, v in hits.items()},
           "identity_values_found": len(found_values), "identity_explained": why,
           "identity_unexplained": unexplained,
           "verdict": "PASS" if not hits["env value"] and not hits["key pattern"] and not unexplained else "FAIL",
           "where": hits}
    print(json.dumps(res, indent=1))
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
