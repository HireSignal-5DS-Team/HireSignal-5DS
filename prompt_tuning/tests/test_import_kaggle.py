"""The Kaggle importer accepts outputs laid out exactly like kaggle_soft_prompt.ipynb's zips and refuses tampered or
unequal ones. Outputs are produced by the real pipeline on a TINY RANDOM Qwen3 (label SMOKE), on all 202 val prompts.
"""
import json
import shutil
import zipfile
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("peft")

from prompt_tuning import common, evaluate, import_kaggle, train_soft_prompt  # noqa: E402
from prompt_tuning.tiny import tiny_lora, tiny_qwen3  # noqa: E402

pytestmark = pytest.mark.skipif(not common.MANIFEST.exists(), reason="run prompt_tuning.prepare_data first")
NEW_TOKENS = 4


@pytest.fixture(scope="module")
def kaggle(tmp_path_factory):
    """/kaggle/working layout: results/<eval run>/..., runs/<train run>/... (checkpoints removed, as in the notebook)."""
    w = tmp_path_factory.mktemp("kaggle_working")
    texts = [m["content"] for ex in common.read_jsonl(common.SFT_TRAIN)[:40] for m in ex["messages"]]
    base = tiny_qwen3(w / "tiny", texts, vocab_size=600)
    lora = tiny_lora(base, w / "tiny_lora")
    tr = ["--base", base, "--revision", "", "--runs-dir", str(w / "runs"), "--max-steps", "1", "--grad-accum", "1",
          "--eval-limit", "2", "--max-len", "8192", "--num-virtual-tokens", "4", "--device", "cpu"]
    train_soft_prompt.train(train_soft_prompt.parse_args(["--run-id", "sp-base-v1", *tr]))
    train_soft_prompt.train(train_soft_prompt.parse_args(["--run-id", "sp-lora-v1", "--lora", lora, *tr]))
    ev = ["--base", base, "--revision", "", "--label", "SMOKE", "--max-new-tokens", str(NEW_TOKENS),
          "--out-root", str(w / "results")]
    runs = {"base": ("base-float32-val", []), "lora": ("lora-float32-val", ["--lora", lora]),
            "soft_prompt": ("sp-base-v1-float32-val", ["--soft-prompt", str(w / "runs/sp-base-v1/soft_prompt")]),
            "lora_soft_prompt": ("sp-lora-v1-float32-val",
                                 ["--lora", lora, "--soft-prompt", str(w / "runs/sp-lora-v1/soft_prompt")])}
    for arm, (rid, extra) in runs.items():
        evaluate.run(evaluate.parse_args(["--arm", arm, "--run-id", rid, *ev, *extra]))
    for d in (w / "runs").glob("*/checkpoint-*"):
        shutil.rmtree(d)
    shutil.make_archive(str(w / "soft_prompt_results"), "zip", w, "results")
    shutil.make_archive(str(w / "soft_prompt_runs"), "zip", w, "runs")
    return {"w": w, "base": base, "lora": lora, "runs": runs}


def args(k, results, runs, dest):
    return ["--results", str(results), "--runs", str(runs), "--dest", str(dest), "--label", "SMOKE",
            "--expect-base", k["base"], "--expect-revision", "", "--expect-lora", k["lora"],
            "--expect-lora-revision", "", "--expect-max-new-tokens", str(NEW_TOKENS)]


def tampered(k, tmp_path, fn):
    """Copy the extracted outputs, apply fn(results_dir, runs_dir), return the import exit code + report."""
    res, runs = tmp_path / "results", tmp_path / "runs"
    shutil.copytree(k["w"] / "results", res)
    shutil.copytree(k["w"] / "runs", runs)
    fn(res, runs)
    code = import_kaggle.main(args(k, res, runs, tmp_path / "dest"))
    return code, json.loads((tmp_path / "dest/IMPORT_REPORT.json").read_text())


def test_clean_import(kaggle, tmp_path):
    w, dest = kaggle["w"], tmp_path / "dest"
    assert import_kaggle.main(args(kaggle, w / "soft_prompt_results.zip", w / "soft_prompt_runs.zip", dest)) == 0
    rep = json.loads((dest / "IMPORT_REPORT.json").read_text())
    assert rep["failures"] == [] and rep["checks_passed"] > 50 and set(rep["arms"]) == set(kaggle["runs"])
    assert rep["arms"]["soft_prompt"]["train"]["train_id"] == "sp-base-v1"
    for rid, _ in kaggle["runs"].values():
        assert (dest / rid / "predictions.jsonl").exists()
    for t in ("sp-base-v1", "sp-lora-v1"):
        assert (dest / "train" / t / "soft_prompt/soft_prompt.safetensors").exists()
    c = json.loads((dest / "COMPARISON.json").read_text())
    assert c["n_paired"] == 202 and c["label"] == "SMOKE"


def _drop_line(res, runs):
    p = res / "lora-float32-val/predictions.jsonl"
    p.write_text("".join(p.read_text().splitlines(keepends=True)[:-1]))


def _edit_json(path, fn):
    d = json.loads(path.read_text())
    fn(d)
    path.write_text(json.dumps(d))


@pytest.mark.parametrize("name,fn,needle", [
    ("missing prediction", _drop_line, "predictions cover 201/202"),
    ("inflated metric", lambda res, runs: _edit_json(res / "sp-base-v1-float32-val/metrics.json",
                                                     lambda d: d["final"].update(macro_f1=0.99)),
     "does not recompute from predictions"),
    ("other dtype", lambda res, runs: _edit_json(res / "base-float32-val/config.json",
                                                 lambda d: d["backend"].update(dtype="bfloat16")),
     "config hash does not recompute"),
    ("swapped soft prompt", lambda res, runs: shutil.copy2(runs / "sp-lora-v1/soft_prompt/soft_prompt.safetensors",
                                                           runs / "sp-base-v1/soft_prompt/soft_prompt.safetensors"),
     "soft prompt sha256 differs"),
    ("other seed", lambda res, runs: _edit_json(runs / "sp-lora-v1/training_args.json", lambda d: d.update(seed=7)),
     "seed 7"),
    ("missing training run", lambda res, runs: shutil.rmtree(runs / "sp-lora-v1"), "not found in the runs archive"),
    ("duplicate arm", lambda res, runs: shutil.copytree(res / "base-float32-val", res / "base-again"),
     "arm base: 2 runs"),
])
def test_refuses_tampered(kaggle, tmp_path, name, fn, needle):
    code, rep = tampered(kaggle, tmp_path, fn)
    assert code == 1, name
    assert any(needle in f for f in rep["failures"]), (name, rep["failures"])
    assert not (tmp_path / "dest/COMPARISON.json").exists()  # nothing imported


def test_refuses_wrong_expectations(kaggle, tmp_path):
    w = kaggle["w"]
    a = args(kaggle, w / "soft_prompt_results.zip", w / "soft_prompt_runs.zip", tmp_path / "d")
    a[a.index("--label") + 1] = "MEASURED"  # SMOKE outputs can never be imported as MEASURED
    assert import_kaggle.main(a) == 1
    rep = json.loads((tmp_path / "d/IMPORT_REPORT.json").read_text())
    assert any("label" in f for f in rep["failures"])


def test_unsafe_zip_members(tmp_path):
    for member in ("../evil.json", "/abs.json", "results/x.py"):
        z = tmp_path / "bad.zip"
        with zipfile.ZipFile(z, "w") as f:
            f.writestr(member, "{}")
        with pytest.raises(ValueError, match="refusing"):
            import_kaggle.safe_extract(z, tmp_path / "out")
