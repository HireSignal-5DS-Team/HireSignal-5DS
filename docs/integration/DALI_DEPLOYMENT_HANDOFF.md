# Deployment handoff for Dali (FastAPI / Docker)

From S6 (orchestrator). Dali owns the deployment code and files. This document only gives you the stable interface
to wrap. Nothing here is a deployment implementation.

## 1. What to pull

| item | value |
|---|---|
| repository | `HireSignal-5DS-Team/HireSignal-5DS` |
| integration branch | `claude/beautiful-galileo-o36bdv` (S6 release candidate; never `main` without the owner's approval) |
| integration commit | see the commit that adds this file (`git log -1 -- docs/integration/DALI_DEPLOYMENT_HANDOFF.md`); newer integration commits are announced in `docs/orchestration/STATUS.md` |
| your branch | create your own, e.g. `feature/deployment`, from that commit. Do not commit to the integration branch. |

## 2. The interface to serve

```python
from matcher.factory import build             # reads the HS_* env vars below
from integration.contract import validate_output, cv_from_reader, job_from_card

pipeline = build()                              # Matcher (LoRA primary + base fallback) -> gated RAG -> validator
                                                # -> Bias Auditor (rules_v2) -> NLI Judge
out = pipeline.run(cv_dict, job_dict)           # dict; validate_output(out) checks it against contract v1.1
```

- **Input**: `CV` and `Job` from `matcher/schemas.py` (v1.0.0, unchanged). JSON Schemas: `integration/schemas/CV.schema.json`
  and `Job.schema.json`. Samples (synthetic): `integration/examples/cv.json` and `job.json`.
- **Output**: `PipelineOutput`, contract `1.1.0`. Pydantic model: `integration/contract.py`. JSON Schema:
  `integration/schemas/PipelineOutput.schema.json`. Requirement ids and evidence quotes (with character spans in the CV
  text) are preserved from input to output.
- **Upstream (Ayoub)**: `cv_from_reader(ReaderResult.to_dict(), cv_id)` and `job_from_card(JobRequirements dict)`.
  Samples: `integration/examples/reader_result.json` and `job_card.json`.
- **Report**: `matcher.pipeline.write_report(out)` gives deterministic Markdown today. The tiny-SLM Report Writer
  (S8, `reporter/`) adds JSON/HTML on top. Its entry point will be announced when it is merged.
- **Never a hiring decision**: every response carries `summary.note`. A requirement with `requires_human_review` must be
  shown as needing review. Do not hide these flags in the UI.

Suggested endpoints (your choice): `POST /match` (CV + Job JSON -> PipelineOutput), `GET /health` (process up),
`GET /ready` (both llama.cpp servers answer `/v1/models` with the expected aliases, RAG index loaded, Judge loaded).

## 3. Models (pinned; `config/matcher_models.json` is the source of truth)

| role | model | revision |
|---|---|---|
| Matcher primary | `Qwen/Qwen3-4B-Instruct-2507` + LoRA `HireSignal-5DS-Team/hiresignal-qwen3-4b-matcher-lora` | base `cdbee75f`, adapter `0b6925b1` |
| Matcher weights | `unsloth/Qwen3-4B-Instruct-2507-GGUF`, `Qwen3-4B-Instruct-2507-Q4_K_M.gguf` | `a06e946b` |
| Matcher fallback | same GGUF, no adapter | — |
| Judge (NLI) | today `MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli` (pretrained, τ 0.65); S7 is evaluating `cross-encoder/nli-deberta-v3-xsmall` and will publish the chosen default | announced on merge |
| Report Writer SLM | `Qwen/Qwen3-0.6B` (S8, in progress) | announced on merge |
| RAG retriever | BM25 over the ESCO ICT subset (`rag/`), gated provider `rag.gated.v1`; Qdrant dense index optional (`HS_RAG=gated-qdrant`, e5-small) | provider `version` string is recorded per result |

Serving: two llama.cpp OpenAI-compatible servers. `scripts/serve_qwen4b_lora.sh <adapter-dir> 8081` converts the PEFT
adapter (`convert_lora_to_gguf.py`, vendored in llama-cpp-python 0.3.16) and serves it with `--lora_path`. The base
server is `python -m llama_cpp.server --model <Q4_K_M.gguf> --model_alias Qwen/Qwen3-4B-Instruct-2507 --n_ctx 4096 --port 8080`.
`python scripts/check_matcher_lora.py --download --workdir <dir>` fetches and verifies the pinned files.

**Port conflict to resolve:** Ayoub's Job Agent defaults to NuExtract on `http://127.0.0.1:8080/v1`
(`HS_NUEXTRACT_BASE_URL`). That is the same port as the Matcher fallback. Give one of them another port in Compose.

## 4. Environment variables

| var | production value | meaning |
|---|---|---|
| `HS_MATCHER_URL` / `HS_MATCHER_MODEL` | `http://matcher-lora:8081/v1` / `Qwen/Qwen3-4B-Instruct-2507+lora` | primary (alias is checked against `/v1/models`) |
| `HS_FALLBACK_URL` / `HS_FALLBACK_MODEL` | `http://matcher-base:8080/v1` / `Qwen/Qwen3-4B-Instruct-2507` | fallback; `HS_FALLBACK=off` disables it |
| `HS_RAG` | `gated` (default) | `gated` \| `bm25` \| `qdrant` \| `gated-qdrant` \| `none` (never `none` in production) |
| `HIRESIGNAL_RAG_DIR` | path to the repo's `rag/` | team RAG code + ESCO data |
| `HS_BIAS_AUDITOR` | `rules_v2` (default) | `rules_v1` \| `rules_v2` \| `rules_v2+reviewer` (reviewer = +1 base-model call/result, opt-in) |
| `HS_JUDGE`, `HS_JUDGE_DIR`, `HS_JUDGE_TAU` | see S7's docs/JUDGE.md once merged | `HS_JUDGE=off` disables the Judge |
| `HS_JSON_SCHEMA` | `off` (default) | constrained decoding, not yet measured: keep off |
| `HS_TIMEOUT`, `HS_MAX_RETRIES` | 300, 2 | per Matcher call |
| `HF_HOME` | a persistent volume | model cache (avoid re-downloads) |

## 5. Dependencies and runtime

- Python 3.13; `requirements-matcher.txt` (pydantic 2.14.1, torch 2.14.1 CPU, transformers 5.19.0, peft 0.21.2, ...);
  `rag/requirements.txt` (bm25s, qdrant-client, sentence-transformers, fastapi, uvicorn, ...);
  `llama-cpp-python[server]==0.3.16`, `gguf`, `mistral_common` (LoRA conversion).
- Proxy note from the cloud build: `download.pytorch.org` was blocked, and the PyPI `torch==2.14.1` wheel worked.
- Measured on 4 vCPU / 15 GiB, CPU only (final locked-test run): LoRA Matcher about 14 s per requirement, base about
  17 s per requirement; one Q4_K_M server about 2.5 GB weights, two servers fit in 15 GiB with the Judge.

## 6. How to test, in this order

1. Mock mode, no models: `pytest integration matcher benchmark/tests tests/qa` must pass. Then `validate_output()`
   on your API response for `integration/examples/{cv,job}.json`.
2. Real mode: both servers up, then `HS_LIVE=1 pytest tests/live` (S5 live suite) and
   `python scripts/run_pipeline.py --cv integration/examples/cv.json --job integration/examples/job.json --out out/ex`.
3. Report the commit you deployed, `/ready` output, and one real response (its `backend` and `provenance` blocks show
   which model answered).

## 7. Known limitations

- bench-v1 is synthetic. Locked-test results are in `docs/orchestration/FINAL_REPORT.md` (after the final run).
- The fine-tuned DeBERTa Judge from 2026-10-15 was never pushed and is lost. The pretrained Judge is the fallback.
- CPU latency is about 14 to 17 s per requirement: use async jobs or streaming for multi-requirement CVs.
- The Profile Agent is not delivered yet; `CV.structured` is optional and never used as evidence.
