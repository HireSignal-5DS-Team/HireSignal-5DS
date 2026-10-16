"""LIVE suite gate. Every test here is skipped unless HS_LIVE=1 AND the model servers answer. Never run in window 0.

Environment (same names as matcher/factory.py):
  HS_LIVE=1                      opt in
  HS_MATCHER_URL                 primary (LoRA) server, default http://127.0.0.1:8081/v1
  HS_FALLBACK_URL                fallback (base) server, default http://127.0.0.1:8080/v1
  HS_RAG                         none | bm25 | qdrant (default bm25; needs HIRESIGNAL_RAG_DIR)
  HS_LIVE_JUDGE=1                also load the NLI Judge (HS_JUDGE_DIR / pretrained); default off
  HS_LIVE_OUT                    output dir (default tests/live/out/<UTC timestamp>)

Output: <out>/provenance.json (servers' /models answers, backend.info(), knowledge, judge, git commit, env) and
<out>/results.jsonl (one line per case: raw model text, validated row, label "LIVE"). A live claim cites this dir.
"""
import datetime as dt
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for p in (ROOT, HERE.parent / "qa", HERE):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

PRIMARY = os.environ.get("HS_MATCHER_URL", "http://127.0.0.1:8081/v1").rstrip("/")
FALLBACK = os.environ.get("HS_FALLBACK_URL", "http://127.0.0.1:8080/v1").rstrip("/")


def models(url, timeout=3.0):
    """The server's /models answer, or None if it does not answer."""
    try:
        with urllib.request.urlopen(f"{url}/models", timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:  # noqa: BLE001
        return None


def pytest_collection_modifyitems(config, items):
    if os.environ.get("HS_LIVE") != "1":
        skip = pytest.mark.skip(reason="LIVE suite: set HS_LIVE=1 (compute window 1+) to run against real models")
        for it in items:
            if HERE in Path(str(it.fspath)).parents:
                it.add_marker(skip)


@pytest.fixture(scope="session")
def servers():
    got = {"primary": models(PRIMARY), "fallback": models(FALLBACK)}
    if got["primary"] is None:
        pytest.skip(f"LIVE: primary Matcher server {PRIMARY} does not answer")
    return got


@pytest.fixture(scope="session")
def pipeline(servers):
    from matcher.factory import build

    env = dict(os.environ)
    env.setdefault("HS_JUDGE", "on" if env.get("HS_LIVE_JUDGE") == "1" else "off")
    if env.get("HS_FALLBACK", "on") != "off" and servers["fallback"] is None:
        env["HS_FALLBACK"] = "off"  # recorded in provenance; the fallback test skips
    try:
        return build(env)
    except FileNotFoundError as e:
        pytest.skip(f"LIVE: knowledge provider unavailable ({e}); set HIRESIGNAL_RAG_DIR or HS_RAG=none")


@pytest.fixture(scope="session")
def recorder(servers, pipeline):
    out = Path(os.environ.get("HS_LIVE_OUT") or HERE / "out" / dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ"))
    out.mkdir(parents=True, exist_ok=True)
    try:
        commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    except OSError:
        commit = None
    prov = {"label": "LIVE", "git_commit": commit, "created_utc": dt.datetime.now(dt.UTC).isoformat(),
            "servers": {"primary": {"url": PRIMARY, "models": servers["primary"]},
                        "fallback": {"url": FALLBACK, "models": servers["fallback"]}},
            "backend": pipeline.matcher.backend.info(), "knowledge": pipeline.matcher.knowledge.name,
            "judge": getattr(pipeline.judge, "name", None),
            "env": {k: v for k, v in os.environ.items() if k.startswith("HS_") and "KEY" not in k and "TOKEN" not in k}}
    (out / "provenance.json").write_text(json.dumps(prov, indent=2, default=str) + "\n")
    fh = (out / "results.jsonl").open("a")

    def record(test, case_id, row, raw=None, **extra):
        fh.write(json.dumps({"label": "LIVE", "test": test, "case_id": case_id, "raw": raw, "row": row, **extra},
                            default=str) + "\n")
        fh.flush()

    record.out = out
    yield record
    fh.close()
