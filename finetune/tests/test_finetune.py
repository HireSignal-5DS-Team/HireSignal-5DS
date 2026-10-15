import json
import shutil
from pathlib import Path

import pytest

from finetune import build_sft, train_lora
from matcher.schemas import ModelAnswer

FIX = Path(__file__).parent / "fixtures" / "train.jsonl"
TINY = "trl-internal-testing/tiny-Qwen2ForCausalLM-2.5"  # 2.4M params, ~4 MB download


@pytest.fixture(scope="module")
def sft(tmp_path_factory):
    out = tmp_path_factory.mktemp("sft")
    build_sft.build(FIX, out, knowledge="none")
    return out


@pytest.fixture(scope="module")
def tok():
    transformers = pytest.importorskip("transformers")
    try:
        return transformers.AutoTokenizer.from_pretrained(TINY)
    except OSError as e:
        pytest.skip(f"tiny model unavailable: {e}")


def rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def test_build_sft_refuses_test_and_val(tmp_path):
    for name in ("test.jsonl", "my_test_copy.jsonl", "val.jsonl"):
        p = tmp_path / name
        shutil.copy(FIX, p)
        with pytest.raises(ValueError):
            build_sft.build(p, tmp_path / "out", knowledge="none")


def test_build_sft_refuses_non_train_split(tmp_path):
    case = json.loads(FIX.read_text().splitlines()[0])
    case["split"] = "test"
    p = tmp_path / "train.jsonl"
    p.write_text(json.dumps(case) + "\n")
    with pytest.raises(ValueError):
        build_sft.build(p, tmp_path / "out", knowledge="none")


def test_build_sft_output(sft):
    train, dev = rows(sft / "sft_train.jsonl"), rows(sft / "sft_dev.jsonl")
    assert len(train) + len(dev) == 10 and dev
    assert not {r["meta"]["case_id"] for r in train} & {r["meta"]["case_id"] for r in dev}  # held out by case
    for r in train + dev:
        assert [m["role"] for m in r["messages"]] == ["system", "user"]
        ans = ModelAnswer.model_validate_json(r["completion"])  # strict schema, same key order as prompt.target
        assert list(json.loads(r["completion"])) == ["decision", "basis", "evidence", "explanation"]
        assert ans.explanation and (ans.evidence or ans.basis in ("not_documented", "ambiguous"))
    # deterministic
    again = sft.parent / "again"
    build_sft.build(FIX, again, knowledge="none")
    assert (again / "sft_train.jsonl").read_text() == (sft / "sft_train.jsonl").read_text()


def test_build_sft_with_rag(tmp_path):
    try:
        build_sft.build(FIX, tmp_path, knowledge="rag")
    except (FileNotFoundError, ImportError) as e:
        pytest.skip(str(e))
    assert any(r["meta"]["rag_refs"] for r in rows(tmp_path / "sft_train.jsonl"))


def test_label_masking(sft, tok):
    ex = rows(sft / "sft_train.jsonl")[0]
    ids, labels = train_lora.encode(tok, ex, 4096, {"enable_thinking": False})
    prompt = tok.apply_chat_template(ex["messages"], tokenize=False, add_generation_prompt=True)
    n_prompt = len(tok(prompt, add_special_tokens=False)["input_ids"])
    assert len(ids) == len(labels)
    assert all(x == -100 for x in labels[:n_prompt])
    kept = labels[n_prompt:]
    assert -100 not in kept and kept == ids[n_prompt:]
    assert tok.decode(kept) == ex["completion"] + tok.eos_token
    assert train_lora.encode(tok, ex, n_prompt, {}) is None  # over max_len -> skipped, not truncated


def test_refuses_test_file():
    with pytest.raises(ValueError):
        train_lora.load_config(None, {"base_model": TINY, "train_file": "benchmark/data/test.jsonl"})


def _cfg(sft, out, **kw):
    return train_lora.load_config(None, {
        "base_model": TINY, "name": "t", "train_file": str(sft / "sft_train.jsonl"),
        "dev_file": str(sft / "sft_dev.jsonl"), "output_root": str(out), "max_steps": 3, "grad_accum": 1,
        "lr": 5e-3, "save_every": 2, "eval_every": 3, "num_threads": 2, "device": "cpu", **kw})


def test_train_save_resume_and_reload(sft, tok, tmp_path):
    torch = pytest.importorskip("torch")
    from peft import PeftModel
    from transformers import AutoModelForCausalLM

    res = train_lora.train(_cfg(sft, tmp_path, max_steps=2))
    run = Path(res["run_dir"])
    assert res["step"] == 2 and (run / "checkpoint-2" / "adapter_model.safetensors").exists()
    res = train_lora.train(_cfg(sft, tmp_path, max_steps=6))  # resumes from checkpoint-2
    assert res["step"] == 6 and (run / "checkpoint-6").exists()
    log = rows(run / "log.jsonl")
    train_losses = [r["train_loss"] for r in log if "train_loss" in r]
    assert [r["step"] for r in log if "train_loss" in r] == list(range(1, 7))
    assert min(train_losses[-2:]) < train_losses[0]  # same tiny data, high lr: loss goes down
    rc = json.loads((run / "run_config.json").read_text())
    assert rc["resumed_from"].endswith("checkpoint-2") and len(rc["data_sha256"]["train"]) == 64
    assert {"torch", "transformers", "peft"} <= set(rc["versions"])

    # reload via plain peft
    base = AutoModelForCausalLM.from_pretrained(TINY)
    m = PeftModel.from_pretrained(base, str(run / "final"))
    assert any("lora_A" in n for n, _ in m.named_parameters())

    # reload via the Matcher backend (adapter_config names the same base id -> compat check passes)
    from matcher.backends import Task, TransformersBackend, check_adapter_compat
    from matcher.schemas import CV, Requirement

    check_adapter_compat(str(run / "final"), TINY)
    be = TransformersBackend(TINY, adapter_id=str(run / "final"), max_new_tokens=4)
    out = be.generate(Task(CV(cv_id="c", text="Python developer"), Requirement(req_id="r", text="Python"), []))
    assert isinstance(out, str)
    with pytest.raises(ValueError):
        check_adapter_compat(str(run / "final"), "Qwen/Qwen3-0.6B")
    del torch


def test_refuses_big_model(monkeypatch, sft, tmp_path):
    monkeypatch.setattr(train_lora, "MAX_PARAMS", 1000)
    with pytest.raises(ValueError, match="< 1B"):
        train_lora.train(_cfg(sft, tmp_path))
