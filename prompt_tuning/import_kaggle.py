"""Import and VALIDATE the outputs of kaggle_soft_prompt.ipynb before any number enters the results table.

  python -m prompt_tuning.import_kaggle --results soft_prompt_results.zip --runs soft_prompt_runs.zip

Inputs are the two zips the notebook writes (or their extracted folders). They are treated as untrusted data:
member paths are checked, nothing in them is executed, only JSON/JSONL/safetensors files are read.

Every check below must pass; otherwise nothing is copied, IMPORT_REPORT.json lists the failures and the exit code is 1.
- each eval run has config.json, metrics.json, predictions.jsonl; exactly one run per arm (4 arms)
- predictions cover exactly the 202 (case_id, req_id) pairs of prompt_tuning/data/val_prompts.jsonl, no duplicates,
  no test case_ids; prompts and gold sha256 equal the committed files; limit 0; label MEASURED
- one setup for all arms: same dtype, device, GPU, torch/transformers/peft versions, greedy, 192 new tokens
- pinned identities: base model + revision for every arm; the Matcher LoRA + revision exactly for the LoRA arms
  and no adapter for the others
- the config hash recomputes from config.json; metrics.json recomputes from predictions.jsonl (benchmark.metrics)
- soft prompt arms: the training run is present; its soft_prompt.safetensors sha256 equals the one the eval
  recorded and the one in provenance.json; it was trained on the committed sft_train.jsonl / sft_val.jsonl /
  manifest (sha256), seed 13, the same dtype, on the right backbone (base vs merged LoRA)
Then copies the runs to benchmark/results/experimental/soft_prompt/kaggle/ and writes COMPARISON.md with compare.py.
"""
import argparse
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

from .common import (BASE, BASE_REVISION, BENCH, LORA, LORA_REVISION, MANIFEST, RESULTS, SFT_TRAIN, SFT_VAL,
                     VAL_PROMPTS, config_hash, read_jsonl, sha256)
from .model import ARMS, SIDE_FILE

READ_SUFFIXES = {".json", ".jsonl", ".md", ".safetensors", ".txt"}
EVAL_FILES = ("config.json", "metrics.json", "predictions.jsonl")
TRAIN_FILES = ("provenance.json", "training_args.json", "environment.json", "loss_log.jsonl", "README.md")


def safe_extract(src, dest):
    """Extract a zip, refusing absolute paths, '..', links and unexpected file types; a folder is copied as is."""
    src, dest = Path(src), Path(dest)
    if src.is_dir():
        shutil.copytree(src, dest, dirs_exist_ok=True, symlinks=True)
        bad = [p for p in dest.rglob("*") if p.is_symlink()]
        if bad:
            raise ValueError(f"refusing symlinks in {src}: {bad[:3]}")
        return dest
    with zipfile.ZipFile(src) as z:
        for info in z.infolist():
            name = info.filename
            parts = Path(name).parts
            if name.startswith(("/", "\\")) or ".." in parts or ":" in name:
                raise ValueError(f"refusing unsafe zip member {name!r}")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError(f"refusing symlink zip member {name!r}")
            if not info.is_dir() and Path(name).suffix not in READ_SUFFIXES:
                raise ValueError(f"refusing unexpected file type {name!r}")
        z.extractall(dest)
    return dest


def find_eval_runs(root):
    return sorted({p.parent for p in Path(root).rglob("config.json") if (p.parent / "predictions.jsonl").exists()})


def find_train_runs(root):
    return {p.parent.name: p.parent for p in Path(root).rglob("provenance.json") if (p.parent / "soft_prompt").is_dir()}


class Checker:
    def __init__(self):
        self.failures, self.passed = [], 0

    def __call__(self, ok, what):
        if ok:
            self.passed += 1
        else:
            self.failures.append(what)
        return ok


def recompute_hash(cfg):
    keys = ("arm", "backend", "prompts_sha256", "gold_sha256", "limit", "max_new_tokens", "dtype", "device", "label")
    c = {k: cfg.get(k) for k in keys}
    c["backend"] = {**cfg["backend"], "load_seconds": None}
    return config_hash(c)


def check_eval_run(d, ck, exp):
    from benchmark import metrics

    rid = d.name
    for f in EVAL_FILES:
        if not ck((d / f).exists(), f"{rid}: missing {f}"):
            return None
    cfg = json.loads((d / "config.json").read_text())
    m = json.loads((d / "metrics.json").read_text())
    recs = read_jsonl(d / "predictions.jsonl")
    be = cfg.get("backend", {})
    arm = cfg.get("arm")
    ck(arm in ARMS, f"{rid}: unknown arm {arm!r}")
    ck(cfg.get("label") == exp["label"] and m.get("label") == exp["label"],
       f"{rid}: label {cfg.get('label')!r}/{m.get('label')!r}, expected {exp['label']!r}")
    ck(cfg.get("limit") == 0, f"{rid}: limit={cfg.get('limit')} (must be 0 = all 202)")
    ck(cfg.get("prompts_sha256") == exp["prompts_sha256"], f"{rid}: prompts sha256 differs from the committed file")
    ck(cfg.get("gold_sha256") == exp["gold_sha256"], f"{rid}: gold sha256 differs from benchmark/data/val.jsonl")
    ck(cfg.get("config_hash") == recompute_hash(cfg) == m.get("config_hash"), f"{rid}: config hash does not recompute")
    keys = [(r["case_id"], r["req_id"]) for r in recs]
    ck(len(keys) == len(set(keys)), f"{rid}: duplicate predictions")
    ck(set(keys) == exp["val_keys"], f"{rid}: predictions cover {len(set(keys) & exp['val_keys'])}/"
                                       f"{len(exp['val_keys'])} val requirements (+{len(set(keys) - exp['val_keys'])} other)")
    ck(not {k[0] for k in keys} & exp["test_ids"], f"{rid}: predictions contain locked test cases")
    ck(be.get("model_id") == exp["base"] and be.get("revision") == exp["revision"],
       f"{rid}: base {be.get('model_id')}@{be.get('revision')}, expected {exp['base']}@{exp['revision']}")
    uses_lora = arm in ("lora", "lora_soft_prompt")
    want = (exp["lora"], exp["lora_revision"]) if uses_lora else (None, None)
    ck((be.get("adapter_id"), be.get("adapter_revision")) == want and bool(be.get("lora_merged")) == uses_lora,
       f"{rid}: adapter {be.get('adapter_id')}@{be.get('adapter_revision')}, expected {want}")
    dec = be.get("decoding", {})
    ck(dec.get("do_sample") is False and dec.get("max_new_tokens") == exp["max_new_tokens"],
       f"{rid}: decoding {dec}, expected greedy with {exp['max_new_tokens']} new tokens")
    if set(keys) == exp["val_keys"] and len(keys) == len(set(keys)):
        rm = metrics.compute(recs)
        same = (rm["n"] == m.get("n") == len(exp["val_keys"]) and rm["json_schema_validity"] == m["json_schema_validity"]
                and all(abs(rm["final"][k] - m["final"][k]) < 1e-9 for k in ("macro_f1", "accuracy"))
                and rm["final"]["false_met_rate"] == m["final"]["false_met_rate"])
        ck(same, f"{rid}: metrics.json does not recompute from predictions.jsonl")
    hw = cfg.get("hardware", {})
    setup = (be.get("dtype"), be.get("device"), hw.get("gpu"), hw.get("torch"), hw.get("transformers"), hw.get("peft"))
    return {"run_id": rid, "dir": d, "arm": arm, "setup": setup, "cfg": cfg, "metrics": m}


def check_train_run(run, ck, exp):
    rid = run["run_id"]
    sp = (run["cfg"]["backend"].get("soft_prompt") or {})
    train_id = Path(str(sp.get("path", ""))).parent.name
    d = exp["train_runs"].get(train_id)
    if not ck(d is not None, f"{rid}: training run {train_id!r} not found in the runs archive"):
        return None
    for f in TRAIN_FILES:
        ck((d / f).exists(), f"{train_id}: missing {f}")
    prov = json.loads((d / "provenance.json").read_text())
    targs = json.loads((d / "training_args.json").read_text())
    side = json.loads((d / "soft_prompt" / SIDE_FILE).read_text())
    st = d / "soft_prompt/soft_prompt.safetensors"
    ck(st.exists() and sha256(st) == sp.get("sha256") == prov.get("soft_prompt_sha256"),
       f"{train_id}: soft prompt sha256 differs between the file, the eval config and provenance.json")
    ck(prov.get("train_sha256") == exp["train_sha256"], f"{train_id}: trained on another sft_train.jsonl")
    ck(prov.get("val_sha256") == exp["val_sha256"], f"{train_id}: selected on another sft_val.jsonl")
    ck(prov.get("manifest_sha256") == exp["manifest_sha256"], f"{train_id}: leak check used another manifest")
    ck(targs.get("seed") == exp["seed"], f"{train_id}: seed {targs.get('seed')}, expected {exp['seed']}")
    ck(targs.get("dtype") == run["setup"][0], f"{train_id}: trained in {targs.get('dtype')}, evaluated in {run['setup'][0]}")
    bb = side.get("backbone", {})
    uses_lora = run["arm"] == "lora_soft_prompt"
    ck(bb.get("base") == exp["base"] and bb.get("base_revision") == exp["revision"] and
       bool(bb.get("lora_merged")) == uses_lora and
       (bb.get("lora"), bb.get("lora_revision")) == ((exp["lora"], exp["lora_revision"]) if uses_lora else (None, None)),
       f"{train_id}: soft prompt backbone {bb} does not match arm {run['arm']}")
    ck(prov.get("train_config_hash") == side.get("train_config_hash") == sp.get("train_config_hash"),
       f"{train_id}: train config hash differs between provenance, soft prompt and eval")
    return {"train_id": train_id, "dir": d, "selected": prov.get("selected"), "steps": prov.get("optimizer_steps")}


def expectations(**over):
    manifest = Path(over.pop("manifest", MANIFEST))
    m = json.loads(manifest.read_text())
    prompts = Path(over.pop("prompts", VAL_PROMPTS))
    exp = {"label": "MEASURED", "base": BASE, "revision": BASE_REVISION, "lora": LORA, "lora_revision": LORA_REVISION,
           "max_new_tokens": 192, "seed": 13, "prompts_sha256": sha256(prompts),
           "gold_sha256": sha256(over.pop("gold", BENCH / "val.jsonl")),
           "val_keys": {(p["case_id"], p["req_id"]) for p in read_jsonl(prompts)},
           "test_ids": set(m["test_case_ids"]), "train_sha256": sha256(over.pop("train", SFT_TRAIN)),
           "val_sha256": sha256(over.pop("val", SFT_VAL)), "manifest_sha256": sha256(manifest)}
    exp.update(over)
    return exp


def validate(results_root, runs_root, exp, require_arms=ARMS):
    ck = Checker()
    exp = {**exp, "train_runs": find_train_runs(runs_root)}
    evals = [e for e in (check_eval_run(d, ck, exp) for d in find_eval_runs(results_root)) if e]
    by_arm = {}
    for e in evals:
        by_arm.setdefault(e["arm"], []).append(e)
    for arm in require_arms:
        ck(len(by_arm.get(arm, [])) == 1, f"arm {arm}: {len(by_arm.get(arm, []))} runs, expected exactly 1")
    ck(len({e["setup"] for e in evals}) == 1, f"arms ran under different setups: {sorted({e['setup'] for e in evals})}")
    trains = {}
    for e in evals:
        if e["arm"] in ("soft_prompt", "lora_soft_prompt"):
            t = check_train_run(e, ck, exp)
            if t:
                trains[e["run_id"]] = t
    return ck, evals, trains


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", required=True, help="soft_prompt_results.zip (or its extracted folder)")
    ap.add_argument("--runs", required=True, help="soft_prompt_runs.zip (or its extracted folder)")
    ap.add_argument("--dest", default=str(RESULTS / "kaggle"))
    ap.add_argument("--label", default="MEASURED", choices=["MEASURED", "SMOKE"], help="SMOKE only for tests")
    ap.add_argument("--expect-base", default=BASE)
    ap.add_argument("--expect-revision", default=BASE_REVISION)
    ap.add_argument("--expect-lora", default=LORA)
    ap.add_argument("--expect-lora-revision", default=LORA_REVISION)
    ap.add_argument("--expect-max-new-tokens", type=int, default=192)
    a = ap.parse_args(argv)
    from . import compare

    exp = expectations(label=a.label, base=a.expect_base, revision=a.expect_revision or None, lora=a.expect_lora,
                       lora_revision=a.expect_lora_revision or None, max_new_tokens=a.expect_max_new_tokens)
    dest = Path(a.dest)
    with tempfile.TemporaryDirectory() as tmp:
        res = safe_extract(a.results, Path(tmp) / "results")
        runs = safe_extract(a.runs, Path(tmp) / "runs")
        ck, evals, trains = validate(res, runs, exp)
        report = {"label": a.label, "checks_passed": ck.passed, "failures": ck.failures,
                  "sources": {"results": str(a.results), "runs": str(a.runs)},
                  "arms": {e["arm"]: {"run_id": e["run_id"], "config_hash": e["cfg"]["config_hash"],
                                      "setup": dict(zip(("dtype", "device", "gpu", "torch", "transformers", "peft"),
                                                        e["setup"])),
                                      "train": {k: v for k, v in trains.get(e["run_id"], {}).items() if k != "dir"}}
                           for e in evals}}
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "IMPORT_REPORT.json").write_text(json.dumps(report, indent=2) + "\n")
        if ck.failures:
            print(json.dumps(report, indent=2))
            print(f"REFUSED: {len(ck.failures)} failed checks; nothing imported", file=sys.stderr)
            return 1
        for e in evals:
            shutil.copytree(e["dir"], dest / e["run_id"], dirs_exist_ok=True)
        for t in trains.values():
            out = dest / "train" / t["train_id"]
            out.mkdir(parents=True, exist_ok=True)
            for f in TRAIN_FILES:
                shutil.copy2(t["dir"] / f, out / f)
            shutil.copytree(t["dir"] / "soft_prompt", out / "soft_prompt", dirs_exist_ok=True)
    c = compare.main(["--out-root", str(dest), "--runs", *(f"{e['arm']}={e['run_id']}" for e in evals)])
    print(f"imported {len(evals)} eval runs and {len(trains)} soft prompts into {dest}; {ck.passed} checks passed")
    return 0 if c else 1


if __name__ == "__main__":
    sys.exit(main())
