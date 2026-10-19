# T02b report — Qwen3-4B + LoRA on llama.cpp, LoRA check

Date: 2026-10-18. No git commands were run. All results below are **real-GPU** (RTX 4050 Laptop, 6 GB).

**Summary:**
- One `llama-server` on port 8090 holds a single Qwen3-4B Q4_K_M with the Matcher LoRA. The adapter is chosen per request.
- Measured:
  - scale 0 gives output byte-identical to a server without the LoRA (30/30 items);
  - scale 1 gives the Matcher;
  - VRAM use is 3,255 MiB of 6,141.
- LoRA check, with knowledge (the main comparison): macro-F1 **0.911 LoRA vs 0.647 base**, valid JSON 1.000 vs 0.900. This is a 30-item smoke test.
- Two things deviate from the task:
  - The newest llama.cpp build is **blocked by Windows Smart App Control**, so I used the older official build b11139.
  - In that build, `--lora-init-without-apply` alone still applies the LoRA by default, so the start script forces the default scale to 0.

## 1. Done

- **llama.cpp** in `tools/llama.cpp/`: official prebuilt release **b11139** (`llama-b11139-bin-win-cuda-12.4-x64.zip`, 2026-09-23) plus the CUDA 12.4 runtime DLLs from `cudart-llama-bin-win-cuda-12.4-x64.zip`. Both zips were checked against GitHub's sha256 digests.
- [scripts/start_llm.ps1](../scripts/start_llm.ps1): start, `-Stop`, and `-NoLora` (plain model only, used for parity checks).
  - It reads `LLM_*` from `.env`, binds to 127.0.0.1:8090, waits for `/health`, then sets the global LoRA scale to 0.
  - Logs go to `tools/llama-server.log*` and the PID to `tools/llama-server.pid` (git-ignored).
- [config/.env.example](../config/.env.example) (placeholders) and `.env` (git-ignored, no secrets):
  - `LLM_PORT`, `LLM_BASE_URL`, `LLM_MODEL=qwen3-4b`, `LLM_MODEL_FILE`, `LLM_LORA_FILE`, `LLM_GPU_LAYERS=all`, `LLM_CTX=4096`, `LLM_SCALE_PLAIN=0`, `LLM_SCALE_MATCHER=1`;
  - `OLLAMA_BASE_URL`, and the cloud backup placeholders;
  - `TESSERACT_CMD` (`.env`: `C:\Program Files\Tesseract-OCR\tesseract.exe`).
- **Ollama:** ran `ollama stop hs-qwen3-4b`; `ollama ps` is empty. [config/ollama/README.md](../config/ollama/README.md) records the status of both Modelfiles.
- [prompts/matcher/v1.md](../prompts/matcher/v1.md): V2 p1 copied with a rule-8 header ("adapted from V2 p1, baseline"), logged in [prompts/PROMPT_LIBRARY.md](../prompts/PROMPT_LIBRARY.md).
- [rag/bm25_esco.py](../rag/bm25_esco.py): only V2's `rag.bm25` provider (BM25 path), stamped per rule 6.
  - Data in `rag/data/esco/esco_ict_skills.jsonl`: 1,621 ESCO ICT concepts, copied from V2 `rag/data/esco/`.
- `data/processed/bench-v1/val.jsonl` + `MANIFEST.json` + `README.md`: the bench-v1 val split, copied from V2.
- [scripts/smoke_matcher.py](../scripts/smoke_matcher.py): LoRA check runner, with arms `base_k`, `lora_k`, `base_0`, `lora_0`, `plain_k`.
- [scripts/check_matcher_parity.py](../scripts/check_matcher_parity.py): offline parity check against V2 (prompt, user message, retrieved ESCO ids).
- Results in [eval/results/2026-10-18_lora_check/](../eval/results/2026-10-18_lora_check/): `config.json`, `items.json`, 4 per-arm `.jsonl` files, `summary.md` / `summary.json`, `NOTES.md`, and `plain_server/` (parity run).
- **End of session (Approver's request):**
  - llama-server stopped with `start_llm.ps1 -Stop`.
  - n8n stopped with a new `-Stop` switch in [scripts/start_n8n.ps1](../scripts/start_n8n.ps1). It stops only `tools\node\node.exe` processes running `tools\n8n`; that was 2 processes, n8n and its task runner.
  - Checked afterwards: nvidia-smi shows 0 MiB used and no GPU processes, and ports 5678, 8010 and 8090 are free.
  - Ollama (11434) is still running as a system service, with no model loaded.

## 2. Evidence

### llama.cpp build and Smart App Control
- **b11716 is blocked.** The latest build (2026-10-17) exits with code `0xC0E90002` and prints nothing. Even `--version` fails.
  - The Code Integrity log (events 3033/3077) says llama-server.exe *"attempted to load …\llama-common.dll that did not meet the Enterprise signing level"*.
  - Smart App Control is on (`VerifiedAndReputablePolicyState = 1`), and the binaries are unsigned (`Get-AuthenticodeSignature`: `NotSigned`).
  - I changed **no** security setting.
  - The GitHub "latest" release `v0.7.0` has no Windows assets; the `bNNNN` builds are now marked prerelease.
- **b11139 runs.** It is the official build from 2026-09-23: `version: 0.4.1-dev (build 11139, commit 42916d83f)`, exit 0. My assumption is that Smart App Control allows it because the files now have cloud reputation; I have not verified this.
- **CUDA choice:** I used the CUDA 12.4 build, not 13.4, because driver 581.86 supports CUDA up to 13.0.
- **Flags**, from `llama-server --help` of b11139:
  - line 164: `--lora FNAME  path to LoRA adapter`;
  - line 708: `--lora-init-without-apply  load LoRA adapters without applying them (apply later via POST /lora-adapters)`;
  - line 132: `-ngl, --n-gpu-layers N … 'auto', or 'all'`; used `all`;
  - `-c 4096`, `--parallel 1`, `--host 127.0.0.1`, `--no-webui`.

### Per-request switching

Matcher prompt v1, same item, `cache_prompt: false`. Requests send `"lora": [{"id": 0, "scale": s}]`.

| check | result |
|---|---|
| scale 0 vs scale 1, 3 items | outputs differ on 3/3. Example `val-002 r4`: s0 `UNCERTAIN`, s1 `MISSING/contradicted` (= gold) |
| scale 0 twice | identical 3/3 |
| request **without** a `lora` field, right after start with `--lora-init-without-apply` | **identical to scale 1** on 3/3, and `/lora-adapters` shows `"scale": 1.0` |
| after `POST /lora-adapters [{"id":0,"scale":0}]` | no field = scale 0. Still true right after a scale-1 request |
| **scale 0 (LoRA loaded) vs server without `--lora`**, 30 items with knowledge | **identical raw output 30/30** (`plain_server/parity.txt`) |

The scale-1 explanations use the same sentences as V2's logged LoRA predictions, for example *"The CV directly shows this requirement; the quote is copied from the CV."*

**VRAM:** 3,255 MiB / 6,141 MiB after loading, and 3,259 MiB during inference (GPU util 67–96%). llama-server is the only GPU process.

**Sampling,** sent per request:
- `temperature 0`, `top_p 1`, `seed 0` from V2 `matcher/backends_api.py:124-125`;
- `max_tokens 192` from `backends_api.py:56` and V2's LoRA run config;
- `repeat_penalty 1.1`: the llama-cpp-python server default V2 ran with (`llama_cpp/server/types.py:64-65`). llama-server's default is 1.00 (`--help` line 266), so it is set explicitly.
- The chat template is the GGUF's own (`--jinja`, the default), which is also what V2's llama-cpp-python used.

### Parity with V2 before running (offline)

`python -B scripts/check_matcher_parity.py . <V2>`:
```
system identical to V2 p1: True
rag_refs identical to V2's logged refs: 30/30; user message identical to V2 user_message(): 30/30
gold: {'MET': 14, 'MISSING': 9, 'UNCERTAIN': 7} pool 202
```
- **The refs were compared with V2's base-RAG run** (`qwen3-4b-q4-rag-val`, 202 rows), not with its LoRA run. V2's LoRA val predictions file (`qwen3-4b-q4+hslora-rag-val/predictions.jsonl`) has only **7 rows**. So the 0.908 recorded for "LIVE val 202" cannot be traced to a full prediction file in V2's results.
- **Line endings:**
  - The copied `val.jsonl` had CRLF line endings (Windows checkout), so its sha256 was `30d91866…`.
  - Normalised to LF, it equals the manifest's `37c60915…`, which is also V2's `dataset_sha256`.
  - I normalised both `val.jsonl` and the ESCO file to LF.

### LoRA check

30 requirements from bench-v1 val (202 total), seed 20261018. The fixed list is in `items.json`.

| arm | adapter scale | knowledge | valid JSON | accuracy | macro-F1 | false-MET | verbatim quotes | mean latency (s) |
|---|---|---|---|---|---|---|---|---|
| base_k | 0 | BM25-ESCO k=3 | 0.900 | 0.633 | 0.647 | 0 | 22/22 | 1.42 |
| **lora_k** | 1 | BM25-ESCO k=3 | **1.000** | **0.933** | **0.911** | 0 | 24/24 | 1.15 |
| base_0 | 0 | none | 0.933 | 0.600 | 0.618 | 0 | 22/22 | 1.32 |
| lora_0 | 1 | none | 1.000 | 0.900 | 0.880 | 1 | 24/24 | 1.09 |

**Smoke test, not a benchmark:** one item is 3.3 accuracy points.

How the metrics are defined:
- **Valid JSON** is strict: the whole reply must be one JSON object with exactly the 4 keys, valid labels, at most 3 quotes and an explanation of at most 600 characters. No repair.
- An invalid reply counts as UNCERTAIN, as in V2's validator.
- Accuracy and macro-F1 use the model's own decision. There is no validator yet.

Readings:
- **The LoRA effect is large in both settings:** +0.26 macro-F1 with knowledge and the same without.
- **Base predictions lean to UNCERTAIN:** 18–19 of 30, against 7 in gold. Its per-class F1 is MET 0.67, MISSING 0.71, UNCERTAIN 0.56. The LoRA has MET F1 1.00 with knowledge.
- **Knowledge vs no knowledge:** +0.03 macro-F1 for both models, which is within noise on 30 items.
- **Comparison with V2's full val:** V2's base-RAG raw macro-F1 is 0.647, and V2 records 0.908 for the LoRA. Our subset numbers are in the same range, but they are not a replication.
- **All base invalid outputs share one failure:** the model copies the label template literally (`"decision": "MET|MISSING|UNCERTAIN"`, 3/30 with knowledge, 2/30 without). Logged as a matcher-v1 failure in the prompt library.
- **Latency** is about 1.1–1.4 s per requirement with no prompt caching.

## 3. Not done / problems

1. **Tesseract:** `C:\Program Files\Tesseract-OCR\tesseract.exe` does not exist yet. The `--version` / `--list-langs` check waits for the Approver's install (T02 report §3.4). `TESSERACT_CMD` is already in `.env`.
2. **llama.cpp b11139 instead of the latest build.** Future llama.cpp updates may be blocked the same way until the new files gain reputation.
3. **Default-scale workaround:** `--lora-init-without-apply` did not keep the adapter off for requests without a `lora` field. The start script fixes it with a POST. Callers should still always send `lora` explicitly.
4. **The llama-server log** at default verbosity doesn't print how many layers were offloaded. The VRAM figure fits a full offload, but I haven't confirmed it from the log.
5. **No security on the server:** llama-server warns "no API key is set and CORS allows all origins". It only listens on 127.0.0.1.
6. **ESCO licence** is not documented in V2. It should be checked in the data/RAG task.

## 4. Questions for the Brain

1. **Smart App Control:** should we stay on b11139, or should the Approver turn Smart App Control off? It is a global security setting. I believe Windows 11 has historically made re-enabling it hard, but I have not verified that. I recommend staying on b11139 unless a later task needs a newer llama.cpp feature.
2. **The Matcher prompt failure** (base copies `MET|MISSING|UNCERTAIN`) only affects the base model, and the Matcher uses the LoRA. Should matcher-v2 still try a fix, such as labels outside the JSON example or JSON-schema constrained output? That would also give the required before/after iteration. Note that changing the prompt the LoRA was trained on can hurt it; this must be measured.
3. **Measurement:** run the full 202-requirement val for `base_k` and `lora_k` now, or wait for the evaluation task? It takes about 10 minutes on this server.

## 5. Suggested next step

1. After the Approver installs Tesseract: verify it with `TESSERACT_CMD`.
2. Then start the first station endpoint on port 8010, the Job Agent ("reuse as-is" in the inventory), calling llama-server with scale 0. Add its n8n node and tests.
