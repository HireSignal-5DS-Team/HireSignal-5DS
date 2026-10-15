"""SMOKE TEST on a RANDOMLY INITIALIZED TINY Qwen2 model (hidden 64, 2 layers, locally trained tokenizer).

It checks the plumbing only: SFT build + test-split refusal, finite loss, checkpointing, resume, adapter reload,
base-mismatch refusal, the < 1B guard and inference through TransformersBackend. It is NOT a fine-tuned
HireSignal model and says nothing about matching quality.
"""
import json
import math
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("transformers")
pytest.importorskip("peft")

from finetune import build_sft, train_lora  # noqa: E402

FIX = Path(__file__).parent / "fixtures/cases_train.jsonl"
TEMPLATE = ("{% for m in messages %}<|im_start|>{{ m['role'] }}\n{{ m['content'] }}<|im_end|>\n{% endfor %}"
            "{% if add_generation_prompt %}<|im_start|>assistant\n{% endif %}")


def tiny_base(path, texts, seed):
    from tokenizers import Tokenizer, models, pre_tokenizers, trainers
    from transformers import PreTrainedTokenizerFast, Qwen2Config, Qwen2ForCausalLM

    specials = ["<|endoftext|>", "<|im_start|>", "<|im_end|>"]
    t = Tokenizer(models.BPE())
    t.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    t.train_from_iterator(texts, trainers.BpeTrainer(vocab_size=400, special_tokens=specials,
                                                     initial_alphabet=pre_tokenizers.ByteLevel.alphabet()))
    from tokenizers import decoders

    t.decoder = decoders.ByteLevel()
    tok = PreTrainedTokenizerFast(tokenizer_object=t, eos_token="<|im_end|>", pad_token="<|endoftext|>")
    tok.chat_template = TEMPLATE
    torch.manual_seed(seed)
    cfg = Qwen2Config(vocab_size=len(tok), hidden_size=64, intermediate_size=128, num_hidden_layers=2,
                      num_attention_heads=4, num_key_value_heads=2, max_position_embeddings=4096,
                      eos_token_id=tok.eos_token_id, pad_token_id=tok.pad_token_id, tie_word_embeddings=True)
    Qwen2ForCausalLM(cfg).save_pretrained(path)
    tok.save_pretrained(path)
    return str(path)


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    root = tmp_path_factory.mktemp("smoke")
    meta = build_sft.build("train", FIX, root / "sft", knowledge="none", test_file=root / "absent.jsonl")
    sft = root / "sft/sft_train.jsonl"
    texts = [m["content"] for ex in build_sft.read_jsonl(sft) for m in ex["messages"]]
    return {"root": root, "sft": sft, "meta": meta, "base": tiny_base(root / "tiny_base", texts, 0),
            "other": tiny_base(root / "tiny_other", texts, 1)}


def args(env, max_steps):
    return train_lora.parse_args(["--base", env["base"], "--train", str(env["sft"]), "--val", str(env["sft"]),
                                  "--run-id", "smoke", "--runs-dir", str(env["root"] / "runs"),
                                  "--max-steps", str(max_steps), "--grad-accum", "2", "--save-every", "1",
                                  "--keep-checkpoints", "2", "--max-len", "4096", "--lr", "1e-3", "--device", "cpu"])


def log(run):
    return [json.loads(x) for x in (run / "loss_log.jsonl").read_text().splitlines()]


def test_sft_meta(env):
    assert env["meta"]["n_examples"] == 3 and len(env["meta"]["source_sha256"]) == 64
    ex = build_sft.read_jsonl(env["sft"])[0]
    assert [m["role"] for m in ex["messages"]] == ["system", "user", "assistant"]
    assert json.loads(ex["messages"][-1]["content"])["decision"] == "MET"


def test_refuses_test_split(env, tmp_path):
    rows = build_sft.read_jsonl(FIX)
    with pytest.raises(AssertionError):
        build_sft.refuse_test("test", FIX, rows, None)
    p = tmp_path / "test.jsonl"
    p.write_text(FIX.read_text())
    with pytest.raises(AssertionError):
        build_sft.refuse_test("train", p, rows, None)
    locked = tmp_path / "locked.jsonl"
    locked.write_text(json.dumps({"case_id": rows[1]["case_id"]}) + "\n")
    with pytest.raises(AssertionError, match="case_ids are in the test split"):
        build_sft.refuse_test("train", FIX, rows, locked)


def test_param_guard():
    train_lora.check_params(999_999_999)
    with pytest.raises(ValueError):
        train_lora.check_params(1_000_000_000)


def test_train_resume_load(env):
    from peft import PeftModel
    from transformers import AutoModelForCausalLM

    from matcher.backends import Task, TransformersBackend, check_adapter_compat
    from matcher.schemas import CV, Requirement

    run = train_lora.train(args(env, 2))
    first = [r for r in log(run) if "loss" in r]
    assert [r["step"] for r in first] == [1, 2] and all(math.isfinite(r["loss"]) for r in first)
    assert (run / "checkpoint-2/state.json").exists() and (run / "checkpoint-2/adapter/adapter_config.json").exists()

    train_lora.train(args(env, 4))  # same run id, more steps: must resume at step 2, not restart
    steps = [r["step"] for r in log(run) if "loss" in r]
    assert steps == [1, 2, 3, 4], steps
    assert sorted(p.name for p in run.glob("checkpoint-*")) == ["checkpoint-3", "checkpoint-4"]
    train_lora.train(args(env, 4))  # finished: idempotent no-op
    assert [r["step"] for r in log(run) if "loss" in r] == [1, 2, 3, 4]
    print("SMOKE losses:", [round(r["loss"], 4) for r in log(run) if "loss" in r], "val:", log(run)[-1])

    adapter = run / "adapter"
    for f in ("adapter_config.json", "adapter_model.safetensors", "tokenizer.json"):
        assert (adapter / f).exists(), f
    for f in ("training_args.json", "provenance.json", "environment.json", "README.md"):
        assert (run / f).exists(), f
    assert json.loads((run / "provenance.json").read_text())["train_sha256"] == build_sft.sha256(env["sft"])

    m = PeftModel.from_pretrained(AutoModelForCausalLM.from_pretrained(env["base"]), adapter)
    assert any("lora_A" in n for n, _ in m.named_parameters())
    check_adapter_compat(str(adapter), env["base"])
    with pytest.raises(ValueError, match="refusing to attach"):
        check_adapter_compat(str(adapter), env["other"])

    be = TransformersBackend(env["base"], adapter_id=str(adapter), max_new_tokens=8)
    out = be.generate(Task(CV(cv_id="c", text="Python 5 years."), Requirement(req_id="r", text="Python"), []))
    assert isinstance(out, str)  # random tiny model: content is noise, only the inference path is checked
