"""Verify (and optionally fetch) the pinned fine-tuned Matcher: LoRA adapter + Qwen3-4B base + Q4_K_M GGUF.

Default mode downloads only small metadata files at the pinned revisions of config/matcher_models.json (safe in compute
window 0, no model loaded) and checks:
  - adapter: PEFT LoRA, base_model_name_or_path == the base model, trained on the pinned base revision (train_meta),
    r / alpha / target modules as pinned; tensor names, ranks and shapes from the safetensors HEADER (range request);
  - tokenizer: adapter tokenizer vocab, merges and special tokens == base tokenizer;
  - chat template: adapter == HF base, and the GGUF's embedded template (read from the GGUF header by range
    request; it is what llama-cpp-python applies) renders the p1 Matcher messages byte-identically.
--download additionally fetches adapter_model.safetensors and the 2.5 GB GGUF (window 1 only) and prints the paths.
Writes a JSON evidence file (--out). Exit code 1 if any check fails.

  python scripts/check_matcher_lora.py --out benchmark/results/matcher_lora_compat.json
  python scripts/check_matcher_lora.py --download --workdir /home/user/hs_models --out <json>
"""
import argparse
import hashlib
import json
import os
import re
import struct
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from matcher import prompt  # noqa: E402
from matcher.schemas import CV, Job  # noqa: E402

CFG = json.loads((ROOT / "config/matcher_models.json").read_text())


def hub_url(repo, sha, f):
    return f"https://huggingface.co/{repo}/resolve/{sha}/{f}"


def http_range(url, start, end):
    headers = {"Range": f"bytes={start}-{end}"}
    if os.environ.get("HF_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['HF_TOKEN']}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120) as r:
        return r.read()


def safetensors_header(url):
    n = struct.unpack("<Q", http_range(url, 0, 7))[0]
    return json.loads(http_range(url, 8, 7 + n))


def gguf_metadata(url, nbytes=16_000_000):
    """GGUF key/values from the file head (arrays summarised by length)."""
    b, p = http_range(url, 0, nbytes - 1), 4
    types = {0: "B", 1: "b", 2: "H", 3: "h", 4: "I", 5: "i", 6: "f", 7: "?", 10: "Q", 11: "q", 12: "d"}

    def rd(fmt):
        nonlocal p
        v = struct.unpack_from("<" + fmt, b, p)[0]
        p += struct.calcsize("<" + fmt)
        return v

    def rs():
        nonlocal p
        n = rd("Q")
        s = b[p:p + n].decode("utf-8", "replace")
        p += n
        return s

    def val(t):
        if t == 8:
            return rs()
        if t == 9:
            et, n = rd("I"), rd("Q")
            return [val(et) for _ in range(n)]
        return rd(types[t])

    assert b[:4] == b"GGUF", "not a GGUF file"
    rd("I"), rd("Q")
    out = {}
    for _ in range(rd("Q")):
        k, t = rs(), rd("I")
        v = val(t)
        out[k] = v if not isinstance(v, list) else f"<array len {len(v)}>"
    return out


def render(template, messages):
    import jinja2

    env = jinja2.Environment(extensions=["jinja2.ext.loopcontrols"])
    return env.from_string(template).render(messages=messages, add_generation_prompt=True)


def p1_messages():
    """p1 prompt on a fixed fictional case (system + user, as the Matcher sends it)."""
    from matcher.schemas import KnowledgeRef

    cv = CV(cv_id="t", text="Experience\n- Set up Maven builds for twelve Java services.")
    job = Job(job_id="j", title="t", requirements=[{"req_id": "r1", "text": "Experience with Apache Maven", "skill_terms": ["Apache Maven"]}])
    ref = KnowledgeRef(source_type="esco", source_id="http://data.europa.eu/esco/skill/maven", title="Apache Maven",
                       text="Apache Maven. Also known as: Maven.", retrieval="fixture")
    return prompt.messages(cv, job.requirements[0], [ref])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="write the evidence JSON here")
    ap.add_argument("--download", action="store_true", help="also fetch adapter weights + GGUF (window 1 only)")
    ap.add_argument("--workdir", default=os.environ.get("HS_MODELS_DIR", "/home/user/hs_models"))
    a = ap.parse_args()
    from huggingface_hub import HfApi, hf_hub_download

    tok = os.environ.get("HF_TOKEN") or None
    base, ad = CFG["base"], CFG["primary"]["adapter"]
    w = base["weights"]
    wd = Path(a.workdir)
    get = lambda repo, sha, f, sub: Path(hf_hub_download(repo, f, revision=sha, token=tok, local_dir=wd / sub))  # noqa: E731
    checks, ev = {}, {"pinned": {"base": base, "adapter": ad}}

    api = HfApi(token=tok)
    for name, repo, sha in [("adapter", ad["repo"], ad["sha"]), ("base", base["model_id"], base["base_revision"]),
                            ("gguf", w["repo"], w["sha"])]:
        info = api.model_info(repo, revision=sha, files_metadata=True)
        ev[f"{name}_hub"] = {"repo": repo, "sha": info.sha, "private": info.private,
                             "files": {s.rfilename: s.size for s in info.siblings if not s.rfilename.endswith(".gguf")
                                       or s.rfilename == w["file"]}}
        checks[f"{name}_sha_resolves"] = info.sha == sha

    adir, bdir = "adapter", "base_config"
    acfg = json.loads(get(ad["repo"], ad["sha"], "adapter_config.json", adir).read_text())
    meta = json.loads(get(ad["repo"], ad["sha"], "train_meta.json", adir).read_text())
    ev["adapter_config"] = {k: acfg.get(k) for k in ("peft_type", "base_model_name_or_path", "revision", "r", "lora_alpha",
                                                     "lora_dropout", "target_modules", "task_type", "use_dora", "use_rslora",
                                                     "modules_to_save", "peft_version")}
    ev["train_meta"] = {k: meta.get(k) for k in ("base", "revision", "steps", "n_train", "n_dev", "versions", "best_checkpoint")}
    ev["train_meta"]["prompt_version"] = (meta.get("data_manifest") or {}).get("prompt_version")
    ev["train_meta"]["train_knowledge"] = (meta.get("data_manifest") or {}).get("train_knowledge")
    ev["train_meta"]["quantization"] = "QLoRA 4-bit NF4 (README); serving uses llama.cpp Q4_K_M"
    checks["peft_lora"] = acfg.get("peft_type") == "LORA" and acfg.get("task_type") == "CAUSAL_LM"
    checks["adapter_base_model"] = acfg.get("base_model_name_or_path") == base["model_id"] == meta.get("base")
    checks["adapter_trained_on_pinned_base_revision"] = meta.get("revision") == base["base_revision"]
    checks["rank_alpha_targets"] = (acfg.get("r"), acfg.get("lora_alpha"), sorted(acfg.get("target_modules") or [])) == \
        (ad["r"], ad["lora_alpha"], sorted(ad["target_modules"]))
    checks["no_modules_to_save_or_dora"] = not acfg.get("modules_to_save") and not acfg.get("use_dora")
    checks["trained_with_prompt_p1"] = ev["train_meta"]["prompt_version"] == prompt.PROMPT_VERSION

    bconf = json.loads(get(base["model_id"], base["base_revision"], "config.json", bdir).read_text())
    hdr = safetensors_header(hub_url(ad["repo"], ad["sha"], "adapter_model.safetensors"))
    hdr.pop("__metadata__", None)
    mods = sorted({re.search(r"\.(\w+_proj)\.lora_", k).group(1) for k in hdr})
    layers = {int(re.search(r"layers\.(\d+)\.", k).group(1)) for k in hdr}
    ranks = {v["shape"][0] for k, v in hdr.items() if "lora_A" in k} | {v["shape"][1] for k, v in hdr.items() if "lora_B" in k}
    ev["adapter_tensors"] = {"count": len(hdr), "modules": mods, "layers": len(layers), "ranks": sorted(ranks),
                             "dtypes": sorted({v["dtype"] for v in hdr.values()}),
                             "non_lora": [k for k in hdr if "lora_" not in k]}
    checks["tensors_cover_all_layers_and_targets"] = (len(layers) == bconf["num_hidden_layers"] and mods == sorted(ad["target_modules"])
                                                     and len(hdr) == 2 * len(mods) * len(layers) and not ev["adapter_tensors"]["non_lora"])
    checks["tensor_rank"] = ranks == {ad["r"]}
    h, kv = bconf["hidden_size"], bconf["num_key_value_heads"] * bconf["head_dim"]
    expect_out = {"q_proj": bconf["num_attention_heads"] * bconf["head_dim"], "k_proj": kv, "v_proj": kv, "o_proj": h,
                  "gate_proj": bconf["intermediate_size"], "up_proj": bconf["intermediate_size"], "down_proj": h}
    expect_in = {**{m: h for m in expect_out}, "o_proj": bconf["num_attention_heads"] * bconf["head_dim"],
                 "down_proj": bconf["intermediate_size"]}
    checks["tensor_shapes_match_base"] = all(
        (v["shape"][1] == expect_in[m] if "lora_A" in k else v["shape"][0] == expect_out[m])
        for k, v in hdr.items() for m in [re.search(r"\.(\w+_proj)\.lora_", k).group(1)])

    lt = json.loads(get(ad["repo"], ad["sha"], "tokenizer.json", adir).read_text())
    bt = json.loads(get(base["model_id"], base["base_revision"], "tokenizer.json", bdir).read_text())
    checks["tokenizer_vocab_merges_special_tokens"] = (lt["model"]["vocab"] == bt["model"]["vocab"]
                                                       and lt["model"]["merges"] == bt["model"]["merges"]
                                                       and lt["added_tokens"] == bt["added_tokens"])
    ev["tokenizer_note"] = ("pre_tokenizer/decoder ByteLevel flags differ (trim_offsets, add_prefix_space: transformers 5 "
                            "re-serialisation); they do not change token ids. llama.cpp uses the GGUF's own tokenizer.")
    btc = json.loads(get(base["model_id"], base["base_revision"], "tokenizer_config.json", bdir).read_text())
    ltpl = get(ad["repo"], ad["sha"], "chat_template.jinja", adir).read_text()
    gmeta = gguf_metadata(hub_url(w["repo"], w["sha"], w["file"]))
    gtpl = gmeta.pop("tokenizer.chat_template", "")
    msgs = p1_messages()
    r_hf, r_ad, r_gg = (render(t, msgs) for t in (btc["chat_template"], ltpl, gtpl))
    ev["chat_template"] = {"adapter_equals_hf_base": ltpl.strip() == btc["chat_template"].strip(),
                           "gguf_equals_hf_base": gtpl.strip() == btc["chat_template"].strip(),
                           "gguf_sha256_16": hashlib.sha256(gtpl.encode()).hexdigest()[:16],
                           "p1_render_sha256_16": hashlib.sha256(r_hf.encode()).hexdigest()[:16],
                           "note": "the GGUF template differs from HF only in assistant-turn <think> handling"}
    checks["chat_template_adapter_equals_base"] = ev["chat_template"]["adapter_equals_hf_base"]
    checks["p1_prompt_renders_identically_hf_adapter_gguf"] = r_hf == r_ad == r_gg
    ev["gguf_metadata"] = {k: gmeta.get(k) for k in ("general.architecture", "general.basename", "general.file_type",
                                                     "qwen3.block_count", "qwen3.embedding_length",
                                                     "qwen3.attention.head_count_kv", "tokenizer.ggml.pre",
                                                     "tokenizer.ggml.eos_token_id", "tokenizer.ggml.tokens")}
    checks["gguf_arch_matches_base"] = (gmeta.get("general.architecture") == bconf["model_type"] == "qwen3"
                                        and gmeta.get("qwen3.block_count") == bconf["num_hidden_layers"]
                                        and gmeta.get("qwen3.embedding_length") == bconf["hidden_size"]
                                        and gmeta.get("tokenizer.ggml.eos_token_id") == bconf["eos_token_id"])

    if a.download:
        ev["paths"] = {"adapter_dir": str(get(ad["repo"], ad["sha"], "adapter_model.safetensors", adir).parent),
                       "base_config_dir": str(wd / bdir), "gguf": str(get(w["repo"], w["sha"], w["file"], "gguf"))}
        json.dump({"repo": ad["repo"], "sha": ad["sha"]}, open(wd / adir / "hs_provenance.json", "w"))
    ev["checks"] = checks
    ev["ok"] = all(checks.values())
    text = json.dumps(ev, indent=2, ensure_ascii=False)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(text + "\n")
    print(json.dumps({"ok": ev["ok"], "failed": [k for k, v in checks.items() if not v], **({"paths": ev["paths"]} if a.download else {})}))
    sys.exit(0 if ev["ok"] else 1)


if __name__ == "__main__":
    main()
