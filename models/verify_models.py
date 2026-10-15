"""Load each arm in models/candidates.json on CPU via matcher.backends.TransformersBackend and smoke-test the
Matcher prompt on 2 hand-made examples. Each arm runs in its own subprocess so memory is freed and RSS is clean.

    python models/verify_models.py                 # all arms -> models/smoke_results.json
    python models/verify_models.py qwen2.5-0.5b    # selected arms (results merged into the same file)

Smoke test only (2 examples): proves the arm loads, counts params and emits parseable JSON. Not a benchmark.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CANDIDATES = ROOT / "models/candidates.json"
OUT = ROOT / "models/smoke_results.json"

CV_TEXT = (
    "Profile: Backend developer.\n"
    "Experience: 2019-2024 Software Engineer at a logistics company. Built REST APIs in Python with FastAPI.\n"
    "Skills: Python, PostgreSQL, Docker.\n"
    "Education: BSc Computer Science.\n"
)
EXAMPLES = [  # (requirement, expected decision, expected basis)
    ({"req_id": "r1", "text": "Experience building REST APIs in Python", "skill_terms": ["Python", "REST API"]},
     "MET", "supported"),
    ({"req_id": "r2", "text": "Kubernetes administration", "skill_terms": ["Kubernetes"]},
     "MISSING", "not_documented"),
]
# The prompt style the Kus-hal adapter was trained on (README example): whole-resume verdict, no system prompt.
NATIVE_KUSHAL = ("Screen this resume for a Backend Engineer position and return a structured verdict. "
                 "Resume: " + CV_TEXT.replace("\n", " "))


def run_arm(arm):
    import psutil
    from huggingface_hub import snapshot_download

    from matcher.agent import Matcher
    from matcher.backends import TransformersBackend
    from matcher.knowledge import NoKnowledge
    from matcher.schemas import CV, Requirement

    rss0 = psutil.Process().memory_info().rss
    be = TransformersBackend(arm["model_id"], adapter_id=arm.get("adapter_id"), revision=arm["revision"],
                             adapter_revision=arm.get("adapter_revision"), max_new_tokens=160,
                             chat_kwargs=arm.get("chat_kwargs"))
    rss = psutil.Process().memory_info().rss
    snap = Path(snapshot_download(arm["model_id"], revision=arm["revision"], local_files_only=True,
                                  allow_patterns="*.safetensors"))
    disk = sum(f.stat().st_size for f in snap.iterdir() if f.suffix == ".safetensors")
    matcher, cv, smoke = Matcher(be, NoKnowledge()), CV(cv_id="smoke", text=CV_TEXT), []
    for req, want_d, want_b in EXAMPLES:
        res, meta = matcher.match_requirement(cv, Requirement(**req))
        smoke.append({"req_id": req["req_id"], "expected": [want_d, want_b], "raw": meta["raw"],
                      "json_parsed": meta["parsed"], "model_decision": res.model_decision,
                      "validated": [res.decision, res.basis], "evidence": res.evidence,
                      "latency_s": round(meta["latency_s"], 2)})
    out = {**arm, "n_params": be.n_params, "load_s": round(be.load_seconds, 2),
           "rss_mb_after_load": round(rss / 2**20), "rss_mb_model_delta": round((rss - rss0) / 2**20),
           "rss_mb_peak": round(psutil.Process().memory_info().rss / 2**20),
           "weights_disk_mb": round(disk / 2**20), "smoke": smoke}
    if arm.get("adapter_id"):  # record the adapter's own output format on its native prompt
        import torch

        msgs = [{"role": "user", "content": NATIVE_KUSHAL}]
        ids = be.tok(be.tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True), return_tensors="pt")
        t0 = time.perf_counter()
        with torch.no_grad():
            gen = be.model.generate(**ids, max_new_tokens=160, do_sample=False, pad_token_id=be.tok.eos_token_id)
        out["native_prompt"] = {"prompt": NATIVE_KUSHAL, "latency_s": round(time.perf_counter() - t0, 2),
                                "raw": be.tok.decode(gen[0, ids["input_ids"].shape[1]:], skip_special_tokens=True)}
    return out


def main(names):
    arms = json.loads(CANDIDATES.read_text())["arms"]
    arms = [a for a in arms if not names or a["name"] in names]
    results = json.loads(OUT.read_text()) if OUT.exists() else {}
    for arm in arms:
        print(f"== {arm['name']}", flush=True)
        p = subprocess.run([sys.executable, __file__, "--one", json.dumps(arm)], capture_output=True, text=True)
        if p.returncode:
            err = (p.stderr.strip().splitlines() or ["(no stderr)"])[-1]
            results[arm["name"]] = {**arm, "error": err}
            print("  ERROR:", err)
        else:
            results[arm["name"]] = json.loads(p.stdout.strip().splitlines()[-1])
            r = results[arm["name"]]
            print(f"  params={r['n_params']:,} load={r['load_s']}s rss={r['rss_mb_after_load']}MB",
                  [(s["json_parsed"], s["model_decision"], s["latency_s"]) for s in r["smoke"]])
        OUT.write_text(json.dumps(results, indent=1, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--one"]:
        print(json.dumps(run_arm(json.loads(sys.argv[2])), ensure_ascii=False))
    else:
        main(sys.argv[1:])
