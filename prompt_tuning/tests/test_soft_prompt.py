"""Tests for the EXPERIMENTAL soft prompt pipeline on a RANDOM TINY Qwen3 model (prompt_tuning/tiny.py).

They check plumbing only: leakage refusals, that only the [n_virtual, hidden] soft prompt trains, checkpoint/resume,
save/load round trip, PEFT generation == manual inputs_embeds generation, backbone-identity refusal, the four-arm
evaluation + comparison. Nothing here measures matching quality.
"""
import json
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("transformers")
pytest.importorskip("peft")

from finetune import build_sft  # noqa: E402
from prompt_tuning import common, compare, estimate, evaluate, train_soft_prompt  # noqa: E402
from prompt_tuning import model as M  # noqa: E402
from prompt_tuning.tiny import tiny_lora, tiny_qwen3  # noqa: E402

FIX = Path(__file__).parents[2] / "finetune/tests/fixtures/cases_train.jsonl"


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    root = tmp_path_factory.mktemp("sp")
    build_sft.build("train", FIX, root / "sft", knowledge="none", test_file=root / "absent.jsonl")
    sft = root / "sft/sft_train.jsonl"
    rows = build_sft.read_jsonl(sft)
    val = root / "sft/sft_valset.jsonl"  # val-like rows for the val-loss path (case_ids renamed to val-*)
    val.write_text("".join(json.dumps({**r, "case_id": "val-" + r["case_id"]}) + "\n" for r in rows))
    manifest = root / "manifest.json"
    manifest.write_text(json.dumps({"val_case_ids": sorted({"val-" + r["case_id"] for r in rows} | {"val-000"}),
                                    "test_case_ids": ["test-000", "test-001"]}))
    texts = [m["content"] for r in rows for m in r["messages"]]
    if common.VAL_PROMPTS.exists():
        texts += [m["content"] for p in common.read_jsonl(common.VAL_PROMPTS)[:5] for m in p["messages"]]
    base = tiny_qwen3(root / "tiny", texts, vocab_size=600)
    return {"root": root, "sft": sft, "val": val, "manifest": manifest, "base": base,
            "lora": tiny_lora(base, root / "tiny_lora"), "rows": rows}


def targs(env, run_id, steps, *extra):
    return train_soft_prompt.parse_args([
        "--base", env["base"], "--revision", "", "--train", str(env["sft"]), "--val", str(env["val"]),
        "--manifest", str(env["manifest"]), "--run-id", run_id, "--runs-dir", str(env["root"] / "runs"),
        "--max-steps", str(steps), "--grad-accum", "2", "--save-every", "1", "--eval-every", "2",
        "--num-virtual-tokens", "4", "--max-len", "8192", "--lr", "5e-2", "--device", "cpu", *extra])


def log(run):
    return [json.loads(x) for x in (run / "loss_log.jsonl").read_text().splitlines()]


# ---------------------------------------------------------------- leakage


def test_leakage_refusals(env):
    rows = env["rows"]
    common.check_no_leakage(rows, {"val-000"}, {"test-000"}, env["sft"])
    with pytest.raises(common.LeakageError, match="val split"):
        common.check_no_leakage(rows, {rows[0]["case_id"]}, set())
    with pytest.raises(common.LeakageError, match="test split"):
        common.check_no_leakage(rows, set(), {rows[1]["case_id"]})
    for name in ("sft_val.jsonl", "test_rows.jsonl"):
        with pytest.raises(common.LeakageError, match="evaluation split"):
            common.check_no_leakage(rows, set(), set(), Path(name))
    with pytest.raises(common.LeakageError, match="not train cases"):
        common.check_no_leakage([{**rows[0], "case_id": "val-007"}], set(), set())


def test_trainer_refuses_val_as_train(env, tmp_path):
    a = targs(env, "leak", 1)
    a.train = str(env["val"])  # file name contains "val"
    with pytest.raises(common.LeakageError):
        train_soft_prompt.train(a)
    a = targs(env, "leak2", 1)
    a.val = str(env["sft"])  # train rows offered as "val" for selection
    with pytest.raises(SystemExit, match="val cases only"):
        train_soft_prompt.train(a)


@pytest.mark.skipif(not common.MANIFEST.exists(), reason="run prompt_tuning.prepare_data first")
def test_committed_data_has_no_leakage():
    m = json.loads(common.MANIFEST.read_text())
    train = common.read_jsonl(common.SFT_TRAIN)
    assert common.check_no_leakage(train, set(m["val_case_ids"]), set(m["test_case_ids"]), common.SFT_TRAIN) == 150
    assert m["files"]["finetune/data/sft_train.jsonl"]["sha256"] == common.sha256(common.SFT_TRAIN)
    assert m["files"]["prompt_tuning/data/val_prompts.jsonl"]["sha256"] == common.sha256(common.VAL_PROMPTS)
    vp = common.read_jsonl(common.VAL_PROMPTS)
    assert len(vp) == 202 and {p["case_id"] for p in vp} <= set(m["val_case_ids"])
    assert all(m["leakage_audit"][s]["case_id_overlap"] == 0 and m["leakage_audit"][s]["exact_cv_duplicates"] == 0
               for s in ("val", "test"))
    sft_val = {(e["case_id"], e["req_id"]): e["messages"][:2] for e in common.read_jsonl(common.SFT_VAL)}
    assert all(sft_val[(p["case_id"], p["req_id"])] == p["messages"] for p in vp)  # same prompts as the team eval
    assert not any("assistant" in [x["role"] for x in p["messages"]] for p in vp)  # no targets in eval prompts


# ---------------------------------------------------------------- shapes, frozen backbone


def test_shapes_only_soft_prompt_trains(env):
    bb, tok, prov = M.load_backbone(env["base"])
    pm = M.new_soft_prompt(bb, env["base"], None, 4, "text", common.INIT_TEXT)
    hidden = bb.config.hidden_size
    tr = M.trainable(pm)
    assert len(tr) == 1 and tr[0].shape == (4, hidden) and tr[0].dtype == torch.float32
    assert all(not p.requires_grad for n, p in pm.named_parameters() if "prompt_encoder" not in n)
    assert M.soft_prompt_tensor(pm).shape == (4, hidden)
    # text init: the virtual tokens start as the embeddings of the first 4 init-text tokens
    ids = tok(common.INIT_TEXT, add_special_tokens=False)["input_ids"][:4]
    emb = bb.get_input_embeddings().weight[ids].float()
    assert torch.allclose(M.soft_prompt_tensor(pm).float(), emb)
    ids = tok("hello world", return_tensors="pt")
    out = pm(**ids)
    assert out.logits.shape == (1, 4 + ids["input_ids"].shape[1], bb.config.vocab_size)
    with pytest.raises(ValueError):
        M.new_soft_prompt(bb, env["base"], None, 4, "vocab")


# ---------------------------------------------------------------- training, resume, selection


def test_train_resume_select(env):
    from safetensors.torch import load_file

    w0 = {n: p.clone() for n, p in M.load_backbone(env["base"])[0].named_parameters()}
    run = train_soft_prompt.train(targs(env, "base-run", 2))
    first = [r for r in log(run) if "loss" in r]
    assert [r["step"] for r in first] == [1, 2] and all(r["loss"] == r["loss"] for r in first)
    assert (run / "checkpoint-2/state.json").exists()
    train_soft_prompt.train(targs(env, "base-run", 4))  # resume, not restart
    assert [r["step"] for r in log(run) if "loss" in r] == [1, 2, 3, 4]
    train_soft_prompt.train(targs(env, "base-run", 4))  # finished: no-op
    assert [r["step"] for r in log(run) if "loss" in r] == [1, 2, 3, 4]
    vals = [r for r in log(run) if "val_loss" in r]
    assert [r["step"] for r in vals] == [2, 4]
    prov = json.loads((run / "provenance.json").read_text())
    best = min(vals, key=lambda r: r["val_loss"])
    assert prov["selected"]["step"] == best["step"] and prov["selected"]["on"] == "val"
    side = json.loads((run / "soft_prompt" / M.SIDE_FILE).read_text())
    assert side["selected_step"] == best["step"] and side["train_config_hash"] == prov["train_config_hash"]
    t = load_file(str(run / "soft_prompt/soft_prompt.safetensors"))["soft_prompt"]
    assert t.shape == (4, 64) and prov["soft_prompt_sha256"] == common.sha256(run / "soft_prompt/soft_prompt.safetensors")
    # the backbone on disk is untouched; the soft prompt moved away from its init
    bb, tok, _ = M.load_backbone(env["base"])
    assert all(torch.equal(w0[n], p) for n, p in bb.named_parameters())
    init = M.new_soft_prompt(bb, env["base"], None, 4, "text", common.INIT_TEXT)
    assert not torch.allclose(M.soft_prompt_tensor(init).float(), t)
    with pytest.raises(SystemExit, match="different args"):
        train_soft_prompt.train(targs(env, "base-run", 4, "--lr", "1e-3"))


def test_cpu_guard(env, monkeypatch):
    monkeypatch.setattr(train_soft_prompt, "CPU_PARAM_LIMIT", 10)
    with pytest.raises(SystemExit, match="CPU training is infeasible"):
        train_soft_prompt.train(targs(env, "guard", 1))


# ---------------------------------------------------------------- save/load, generation paths


def test_save_load_and_inputs_embeds_equivalence(env):
    from safetensors.torch import load_file

    from prompt_tuning.backend import SoftPromptBackend

    run = train_soft_prompt.train(targs(env, "gen-run", 2))
    sp = run / "soft_prompt"
    be = SoftPromptBackend("soft_prompt", env["base"], soft_prompt=str(sp), max_new_tokens=12)
    assert torch.allclose(M.soft_prompt_tensor(be.model).float(), load_file(str(sp / "soft_prompt.safetensors"))["soft_prompt"])
    msgs = env["rows"][0]["messages"][:2]
    out1, out2 = be.generate_messages(msgs), be.generate_messages(msgs)
    assert out1 == out2 and isinstance(out1, str)  # greedy: deterministic
    # the same answer without PEFT: concat(soft prompt, token embeddings) -> generate(inputs_embeds=...)
    bb, tok, _ = M.load_backbone(env["base"])
    ids = tok(be.render(msgs), return_tensors="pt", add_special_tokens=False)["input_ids"]
    t = load_file(str(sp / "soft_prompt.safetensors"))["soft_prompt"].to(bb.dtype)
    emb = torch.cat([t[None], bb.get_input_embeddings()(ids)], dim=1)
    with torch.no_grad():
        o = bb.generate(inputs_embeds=emb, attention_mask=torch.ones(emb.shape[:2], dtype=torch.long),
                        max_new_tokens=12, do_sample=False, pad_token_id=tok.pad_token_id)
    assert tok.decode(o[0], skip_special_tokens=True) == out1
    # and the soft prompt matters: the base arm (no soft prompt) is a different computation
    base_be = SoftPromptBackend("base", env["base"], max_new_tokens=12)
    with torch.no_grad():
        lp = be.model(input_ids=ids).logits[0, -1]
        lb = base_be.model(input_ids=ids).logits[0, -1]
    assert not torch.allclose(lp, lb)


def test_lora_soft_prompt_and_backbone_refusal(env):
    from prompt_tuning.backend import SoftPromptBackend

    sp_base = train_soft_prompt.train(targs(env, "gen-run", 2)) / "soft_prompt"
    sp_lora = train_soft_prompt.train(targs(env, "lora-run", 2, "--lora", env["lora"])) / "soft_prompt"
    side = json.loads((sp_lora / M.SIDE_FILE).read_text())
    assert side["backbone"]["lora_merged"] and side["backbone"]["lora"] == env["lora"]
    # merged LoRA changes the backbone, so the two frozen networks differ
    b0, _, _ = M.load_backbone(env["base"])
    b1, _, _ = M.load_backbone(env["base"], lora=env["lora"])
    assert not all(torch.equal(p, q) for p, q in zip(b0.parameters(), b1.parameters()))
    assert not any("lora" in n for n, _ in b1.named_parameters())  # merged: a plain Qwen3 model
    be = SoftPromptBackend("lora_soft_prompt", env["base"], lora=env["lora"], soft_prompt=str(sp_lora), max_new_tokens=6)
    assert isinstance(be.generate_messages(env["rows"][0]["messages"][:2]), str)
    assert be.info()["lora_merged"] and be.info()["soft_prompt"]["shape"] == [4, 64]
    with pytest.raises(ValueError, match="refusing to attach"):
        SoftPromptBackend("lora_soft_prompt", env["base"], lora=env["lora"], soft_prompt=str(sp_base))
    with pytest.raises(ValueError, match="refusing to attach"):
        SoftPromptBackend("soft_prompt", env["base"], soft_prompt=str(sp_lora))
    with pytest.raises(ValueError, match="needs --lora"):
        M.build_arm("lora", env["base"])
    with pytest.raises(ValueError, match="must not get --soft-prompt"):
        M.build_arm("base", env["base"], soft_prompt=str(sp_base))


# ---------------------------------------------------------------- evaluation + comparison


@pytest.mark.skipif(not common.VAL_PROMPTS.exists(), reason="run prompt_tuning.prepare_data first")
def test_four_arm_eval_and_compare(env, tmp_path):
    sp_base = train_soft_prompt.train(targs(env, "gen-run", 2)) / "soft_prompt"
    sp_lora = train_soft_prompt.train(targs(env, "lora-run", 2, "--lora", env["lora"])) / "soft_prompt"
    out = tmp_path / "res"
    ev = ["--base", env["base"], "--revision", "", "--label", "SMOKE", "--limit", "3", "--max-new-tokens", "8",
          "--out-root", str(out)]
    arms = {"base": [], "lora": ["--lora", env["lora"]], "soft_prompt": ["--soft-prompt", str(sp_base)],
            "lora_soft_prompt": ["--lora", env["lora"], "--soft-prompt", str(sp_lora)]}
    for arm, extra in arms.items():
        m = evaluate.run(evaluate.parse_args(["--arm", arm, "--run-id", arm, *ev, *extra]))
        assert m["n"] == 3 and m["label"] == "SMOKE" and len(m["config_hash"]) == 64
        assert m["peak_rss_mb"] > 0 and m["latency_s"]["p95"] >= m["latency_s"]["p50"]
        recs = common.read_jsonl(out / arm / "predictions.jsonl")
        assert {"decision", "model_decision", "parsed", "raw", "gold_decision", "latency_s"} <= set(recs[0])
    evaluate.run(evaluate.parse_args(["--arm", "base", "--run-id", "base", *ev]))  # resume: nothing new
    assert len(common.read_jsonl(out / "base/predictions.jsonl")) == 3
    with pytest.raises(SystemExit, match="another configuration"):
        evaluate.run(evaluate.parse_args(["--arm", "base", "--run-id", "base", *ev, "--max-new-tokens", "9"]))
    c = compare.main(["--out-root", str(out), "--runs", *(f"{a}={a}" for a in arms)])
    assert c["label"] == "SMOKE" and c["n_paired"] == 3 and len(c["rows"]) == 4
    assert all("mcnemar_vs_base" in r for r in c["rows"] if r["arm"] != "base")
    assert "SMOKE" in (out / "COMPARISON.md").read_text()


def test_evaluate_refuses_test_prompts(tmp_path):
    p = tmp_path / "test_prompts.jsonl"
    p.write_text(json.dumps({"case_id": "val-000"}) + "\n")
    with pytest.raises(AssertionError, match="locked test"):
        evaluate.refuse_test(p, common.read_jsonl(p), tmp_path / "none.json")
    q = tmp_path / "prompts.jsonl"
    q.write_text(json.dumps({"case_id": "test-003"}) + "\n")
    man = tmp_path / "m.json"
    man.write_text(json.dumps({"test_case_ids": ["test-003"], "val_case_ids": []}))
    with pytest.raises(AssertionError, match="locked test"):
        evaluate.refuse_test(q, common.read_jsonl(q), man)


def test_compare_refuses_unequal_setups(tmp_path):
    def fake(run, dtype, label="SMOKE"):
        d = tmp_path / run
        d.mkdir()
        (d / "metrics.json").write_text(json.dumps({"label": label, "backend": {"dtype": dtype, "device": "cpu",
                                                                                 "decoding": {"max_new_tokens": 192}}}))
        (d / "predictions.jsonl").write_text("")
    fake("a", "float16")
    fake("b", "bfloat16")
    fake("c", "float16", "MEASURED")
    with pytest.raises(SystemExit, match="unequal comparison"):
        compare.compare({"base": "a", "lora": "b"}, tmp_path)
    with pytest.raises(SystemExit, match="mix labels"):
        compare.compare({"base": "a", "lora": "c"}, tmp_path)


def test_mcnemar_and_param_count():
    assert compare.mcnemar([True] * 5, [True] * 5)["p"] == 1.0
    r = compare.mcnemar([True] * 10 + [False] * 10, [False] * 10 + [True] * 10)
    assert r["a_only"] == 10 and r["b_only"] == 10 and r["p"] == 1.0
    assert compare.mcnemar([True] * 10, [False] * 10)["p"] < 0.01
    p = estimate.n_params(estimate.QWEN3_4B)
    assert 4.0e9 < p["total"] < 4.05e9  # Qwen3-4B: 4.02 B parameters (model card)
    assert common.config_hash({"a": 1, "b": 2}) == common.config_hash({"b": 2, "a": 1})
