# Fine-tuned Matcher integration (Session 2)

Branch `session/s2-matcher-lora-integration`. Status on 2026-10-16: **code and mock tests done, compatibility verified
from Hub metadata; nothing has run on a real model in this pipeline yet** (compute window 0). The live smoke test is
ready for window 1 (`scripts/live_smoke.sh`).

## 1. Models

| role | model | served as |
|---|---|---|
| primary | `Qwen/Qwen3-4B-Instruct-2507@cdbee75f17c01a7cc42f958dc650907174af0554` + LoRA `HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora@0b6925b1e3c89b6b266b10bcd30af4c6a0c2dc3a` | llama.cpp (llama-cpp-python 0.3.16) on `unsloth/Qwen3-4B-Instruct-2507-GGUF@a06e946bb6b655725eafa393f4a9745d460374c9` `Q4_K_M`, adapter converted to f16 GGUF, `--lora_path`, alias `Qwen/Qwen3-4B-Instruct-2507+lora`, port 8081 |
| fallback | the same base, no adapter | same GGUF and runtime, alias `Qwen/Qwen3-4B-Instruct-2507`, port 8080 |

The pins live in `config/matcher_models.json`. `matcher/factory.py` reads them. `HS_LORA_REPO` / `HS_LORA_SHA` override
the adapter only when another revision is served on purpose, and the override is recorded. The 202-requirement eval
run (`benchmark/results/adapter/hs_lora_provenance.json`, read-only) pinned the same sha. A test checks that the two
agree.

## 2. Compatibility evidence (Hub metadata only, no model loaded)

Reproduce: `python scripts/check_matcher_lora.py --out docs/matcher_integration/lora_compat.json`. It downloads a few
small files at the pinned revisions and reads two file headers by HTTP range request. Result: **16/16 checks pass**
(`docs/matcher_integration/lora_compat.json`).

| check | evidence |
|---|---|
| adapter type | PEFT 0.21.2 `LORA`, `CAUSAL_LM`, no DoRA/rsLoRA, no `modules_to_save` |
| base model | `base_model_name_or_path = Qwen/Qwen3-4B-Instruct-2507`. `train_meta.json` revision `cdbee75f…` is the pinned base revision |
| rank / targets | r=16, alpha 32, dropout 0.05, targets q,k,v,o,gate,up,down_proj |
| tensors (safetensors header) | 504 F32 tensors = 36 layers × 7 modules × (A,B); rank 16 everywhere; every A/B shape matches the base `config.json` (hidden 2560, 32 heads × 128, 8 KV heads, intermediate 9728); no embedding or lm_head tensors |
| tokenizer | adapter `tokenizer.json` vocab (151,643), merges and the 26 added/special tokens are identical to the base. Only ByteLevel `trim_offsets` / `add_prefix_space` flags differ (a transformers 5 re-serialisation). They do not change token ids. llama.cpp uses the GGUF's own tokenizer anyway |
| chat template | adapter `chat_template.jinja` is identical to the base template. The GGUF embeds a different template (Unsloth's edit of the assistant `<think>` handling). llama-cpp-python 0.3.16 applies that GGUF template (`Jinja2ChatFormatter` from `tokenizer.chat_template`). Rendered on the p1 Matcher messages (system + user + generation prompt), HF base, adapter and GGUF templates give **byte-identical** prompts |
| GGUF | `qwen3`, 36 blocks, embedding 2560, KV heads 8, eos 151645 (`<|im_end|>`), `file_type` 15 (Q4_K_M) |
| prompt | the adapter was trained with prompt `p1` and BM25-ESCO knowledge (k=3), which is the production prompt and RAG |
| converter | `convert_lora_to_gguf.py` (vendored in llama-cpp-python 0.3.16) needs only the base `config.json`, not the weights |

Known gaps (not blockers, but they are differences between training and serving):
- The adapter was trained as **QLoRA on a 4-bit NF4 base** (bitsandbytes). It is served on a **llama.cpp Q4_K_M** base.
  The two quantisations differ, so the adapter's effect is not guaranteed to transfer exactly. The 202-requirement
  eval measures exactly this serving configuration; this repository does not claim a number for it.
- `train_meta.json` reports 50 optimiser steps for 777 examples × 2 epochs (`expected_steps` 98; the difference is
  consistent with a per-device batch of 2 × grad-accum 16). The dev loss is 0.018. Nothing here measures quality.
- The training data manifest has 0 human-labelled real pairs: it is synthetic bench data plus ContractNLI.

## 3. Output path and guarantees

```
raw text --parse_model_output (frozen, strict)--> ModelAnswer
        \--fails--> output_adapters.strict_repair (form only) --> ModelAnswer | None
ModelAnswer | None --validate (frozen)--> RequirementResult --route (matcher review reasons)--> MatchReport
```

`strict_repair` never maps synonyms (`YES`, `MATCH`, `NOT_MET`, …). It never derives a decision or a basis, and it
never picks from a copied template (`MET|MISSING`). It only fixes form: code fences, `<think>` blocks, a Python-literal
dict, key case, extra keys, label case/spaces/hyphens, a string instead of a list of quotes, more than 3 quotes, a
missing or over-long explanation, and output cut by `max_tokens` **inside the explanation**. In that last case the
decision, the basis and the complete evidence list must already be present. Anything else gives `None`, so the
validator returns UNCERTAIN + `model_output_invalid`. Every quote still goes through the exact-substring check.

The Matcher does **not** fall back on a bad answer, only on a transport failure (error after retries). A model that
answers badly is reported, not silently replaced.

## 4. Provenance format

`MatchReport.backend` (free-form dict in the frozen schema):

```jsonc
{
  "backend": "fallback", "primary": {...info + provenance...}, "fallback": {...},
  "knowledge": "rag.bm25", "knowledge_provider": "rag.bm25", "knowledge_version": null, "prompt_id": "p1",
  "results": {                       // one entry per requirement: the model that actually answered it
    "r1": {
      "answered_by": "primary",      // "primary" | "fallback" | "single" | null (every endpoint failed)
      "role": "primary", "model_id": "Qwen/Qwen3-4B-Instruct-2507",
      "served_alias": "Qwen/Qwen3-4B-Instruct-2507+lora",
      "base_revision": "cdbee75f17c01a7cc42f958dc650907174af0554",
      "weights": {"repo": "unsloth/Qwen3-4B-Instruct-2507-GGUF", "sha": "a06e946b…", "file": "…Q4_K_M.gguf", "quant": "Q4_K_M"},
      "adapter": {"repo": "HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora", "sha": "0b6925b1…", "r": 16, …},  // null on the fallback
      "runtime": "llama.cpp (llama-cpp-python 0.3.16 server), OpenAI-compatible", "endpoint": "http://127.0.0.1:8081/v1",
      "alias_verified": true,        // alias listed by GET /v1/models; false = another model is served; null = not checked
      "served_aliases": ["Qwen/Qwen3-4B-Instruct-2507+lora"],
      "knowledge_provider": "rag.bm25", "knowledge_version": null, "prompt_id": "p1",
      "repairs": [], "finish_reason": "stop", "error": null, "primary_error": null
    }
  }
}
```

The pipeline output (`scripts/run_pipeline.py`, `report.json`) carries the same dict per row (`provenance`) and the full
MatchReport (`match_report`). The markdown report prints an "Answered by" line per requirement.

Why `alias_verified`: llama-cpp-python answers any requested `model` with its default model and echoes the requested
name in the response. The response's `model` field therefore proves nothing. The alias list at `/v1/models` is the
only server-side signal (checked once per backend instance, re-checked while unreachable).

Backends that are not HTTP model endpoints (scripted fakes, MockBackend, lexical baseline) are marked
`"MOCK": true` in provenance, and the markdown report says "MOCK backend: not a model result".

`knowledge_version` is `null` until S1 adds a `version` attribute to the providers
(`docs/orchestration/requests/s2-knowledge-version.md`).

## 5. Human review rules

Review is routing, never rejection. No rule changes a decision. Matcher reasons (`matcher/agent.py:MATCHER_REVIEW`)
are added to the validator's reasons in both the MatchReport (`review_reasons`, `needs_human_review`,
`review_priority`) and the pipeline rows:

| reason | when | priority |
|---|---|---|
| `matcher:backend_unavailable` | every endpoint failed; the decision is the validator's UNCERTAIN | high |
| `matcher:output_unparseable` | a model answered, but no ModelAnswer could be read even after repair | high |
| `matcher:served_model_mismatch` | the endpoint does not list the requested alias | high |
| `matcher:fallback_model_used` | the base model answered instead of the fine-tuned primary | medium |
| `matcher:output_repaired` | the answer needed a form repair beyond code fence / think block | medium |
| `matcher:counterfactual_mixed_models` | live counterfactual variants were not all answered by the same model, so a flip may be a model switch | medium |
| `matcher:met_weak_evidence` | MET whose every verified quote reads as learning, hobby or intent only (`agent.WEAK_EVIDENCE`) | high |

The validator's own reasons (`matcher/validate.py`) still apply: fabricated or non-verbatim evidence, MET without
evidence, years below the minimum, inconsistent decision/basis, UNCERTAIN, and a must-have MISSING (absence of
evidence is not proof of absence). Bias Auditor and Judge findings are added in `matcher/pipeline.py:aggregate`.
Citations: `rag_refs` = the `source_id`s of exactly the knowledge entries placed in the prompt (same list object).
`citations[].shown_as` is the label the prompt shows.

## 5b. Follow-ups to the LIVE LoRA val evaluation (eval branch `claude/kind-albattani-k7qlt9` @ `46d24e1`)

- **Template explanations.** The LoRA writes fixed explanations that never name the requirement. The aggregator now adds
  `explanation_grounded`, built only from the requirement text, the validated decision, the verified CV quotes and the
  titles of the cited knowledge entries. The model's text stays in `explanation`; the report shows both. The
  consolidated "on topic" proxy is satisfied by construction, because the text names the requirement. It is **not**
  a quality gain. What the test checks is that every quoted string is a verified CV substring.
- **False-MET (0.009 base -> 0.026/0.034 LoRA).** In the committed LIVE predictions, 2 of the LoRA false-METs were
  already routed by `duration_not_verified`. The rest rest on hedged quotes ("Watched tutorials about React in spare
  time."). `matcher:met_weak_evidence` sends such a MET to review and keeps the decision. **Val-tuned; held-out effect
  unmeasured.** The rule was designed after seeing these val errors, so it routing 3/3 (no RAG) and 4/4 (RAG) of them is
  in-sample. Out-of-sample false-alarm check on train gold: it fires on **0 of 305** MET requirements (0/305 quotes). The
  held-out effect will come from the locked test split in the orchestrator's final run.
- **Adapter `n/a` in the consolidated table.** `benchmark.run` builds `OpenAICompatBackend` without provenance. A local
  endpoint serving a pinned alias now takes the pin (`backends_api.default_provenance`), so `info()` carries
  `adapter_id` and `adapter_revision`. Hosted or unknown aliases get none, not a guess. The orchestrator regenerates
  the table.

## 6. Contracts used (unchanged)

Frozen files are untouched: `matcher/schemas.py`, `matcher/json_schemas/`, `matcher/validate.py`, `matcher/prompt.py`.
Knowledge provider `lookup(req, k, job_id=None)` (S1); Bias Auditor `check_result` / `counterfactual` (S4) receive
validated results and never change a decision; the Judge (S5) adds findings only; Aggregator and Report Writer are in
`matcher/pipeline.py`. The production default keeps RAG on (`HS_RAG` unset = `bm25`). A test pins this.

## 7. Tests

Mock (run anywhere): `pytest matcher benchmark/tests` gives **75 passed, 6 skipped**. The skips are 2 tests that need
the RAG checkout or torch, and 4 live tests. `matcher/tests/test_matcher_integration.py` runs the real
`OpenAICompatBackend` / `FallbackBackend` / factory over HTTP against fake llama.cpp servers that mimic llama-cpp-python
(alias echo, `/v1/models`). It covers provenance per result, the JSON-schema-file validation of the MatchReport,
citations, fallback, both-down, malformed JSON (unparseable, synonym, template, truncated), alias mismatch, review of
must-have MISSING, MOCK labelling, the pinned config, the production default, and mixed-model counterfactuals.
**All answers in these tests are scripted (MOCK).**

Live (window 1 only):

```bash
HS_COMPUTE_WINDOW=1 HIRESIGNAL_RAG_DIR=<team rag dir> scripts/live_smoke.sh            # val-000,val-001,val-002
```

The script refuses to run without `HS_COMPUTE_WINDOW=1` and takes `/home/user/hs_queue.lock`. It refuses if a model
server is already on 8080/8081. It verifies and fetches the pinned adapter, base `config.json` and Q4_K_M GGUF
(`scripts/check_matcher_lora.py --download`), then starts both servers. It runs `HS_LIVE=1 pytest
matcher/tests/test_live_matcher.py` and `scripts/live_smoke.py` (3 cases through the full pipeline, plus a
forced-fallback run), then stops the servers. Artefacts go to `benchmark/results/live_smoke/<UTC>/`: `smoke.json`
(checks, summary, provenance), `predictions.jsonl`, `report-*.json|md`, `forced-fallback.json`, server logs and
`/v1/models` answers. The smoke label says LIVE only when this script started the servers. 3 cases are a smoke test,
not an accuracy number.

Prerequisites for the live run: llama-cpp-python 0.3.16 with the server extra, its vendored llama.cpp source
(`LLAMA_CPP_SRC`) for `convert_lora_to_gguf.py`, plus torch, safetensors, gguf, huggingface_hub, jinja2,
jsonschema (optional) and the RAG code. About 2 × 2.5 GB RAM for the two servers.

Harness dry-run (MOCK): `test_live_matcher.py` and `live_smoke.py` were run once against two fake servers that answer
with the gold labels. Result: 4/4 tests passed and all smoke checks passed on 13 requirements. That checks only that the
harness works. It is not a model result, and nothing from it is committed as one.

## 8. Not verified yet

- Any live output of the LoRA Matcher through this pipeline: JSON-valid rate, repairs, latency, provenance on a real
  server. Waits for window 1.
- `convert_lora_to_gguf.py` on this adapter and llama.cpp loading it (the eval session did this in its own container;
  this session did not).
- That llama-cpp-python's `/v1/models` lists the `--model_alias` (read from the 0.3.16 source, not observed live).
- The effect of the NF4-trained adapter on a Q4_K_M base (measured by the separate 202-requirement eval, not here).
- The NLI Judge and the inline counterfactual audit on LoRA outputs (S5 / S4 live work).
- `knowledge_version` (S1 request open).
