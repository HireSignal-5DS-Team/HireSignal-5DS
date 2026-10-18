# Reuse inventory — team V2 (read-only)

Source: `C:\Users\semah\HireSignal-Integration\v2-agent-integration`, branch `feature/agent-integration`, **HEAD `a5a03ff`** (working tree clean).
CLAUDE.md names `725923b` as the reference commit. `725923b` is an ancestor of HEAD; HEAD has two more commits:
`0593d6a` (retry transient Qwen 5xx once) and `a5a03ff` (Windows one-command startup script). See question 1 in `tasks/T01_report.md`.

Method: read-only file reads and read-only git commands (`log`, `branch --show-current`, `status --short`, `merge-base --is-ancestor`). Nothing was run, installed or copied.
Test counts and metrics below are what V2's own files say, **not re-run by us**. Lines marked "verified" were re-read by hand during T01.

What the V2 request runs today (`integration/upstream.py`, `POST /api/v2/analyze`):
Reader → Profile (anonymise, then plain Qwen3-4B parse) → Job Agent (job-q1, plain Qwen3-4B) → Matcher (Qwen3-4B Q4_K_M + LoRA `0b6925b1`, gated BM25 RAG over ESCO) → validator v2 → Bias rules_v2 → DeBERTa-v3-xsmall NLI Judge → aggregate → Report Writer (deterministic text, plus Qwen3-0.6B Q8_0 with validation and fallback).
It is one FastAPI endpoint, the "black-box `/analyze`" that our Locked architecture replaces with one n8n node per station.

---

## 1. Reader

- **V2 files:**
  - `agents/reader/reader.py`: tools only, no AI model.
    - Text PDFs go through PyMuPDF, with two-column detection.
    - Scanned PDFs: a page with fewer than 50 characters counts as a scan. It is rendered at 300 DPI and read with Tesseract.
    - DOCX goes through python-docx.
    - Images go through Pillow cleanup (OSD rotation, upscale, column crop, median-filter retry), then Tesseract.
    - TXT is read as UTF-8, UTF-16 or cp1252.
    - It returns a `ReaderResult` with text, sections, ocr_confidence and needs_human_review (set when confidence < 60 or text < 200 characters).
  - `agents/reader/cleaning.py`, `agents/reader/sections.py` (EN/FR heading rules), `agents/reader/README.md`, `scripts/read_cv.py`.
  - `integration/upstream.py:68-82` limits uploads to 10 MB and an extension whitelist.
- **Verdict: adapt.**
  - The OCR/text path is solid. The **vision-model path and late fusion are not in V2** (no VLM anywhere) and have to be written new.
- **Tests:**
  - `tests/test_reader.py` (26): real code and real Tesseract on generated PDF, DOCX and image files. No LLM. Real.
  - `integration/tests/test_upstream.py` uses the real Reader.
  - Never run on this laptop, because Tesseract is not installed (see T01 report).
- **Dependencies:**
  - From `requirements.txt` (unpinned): `pymupdf>=1.24`, `python-docx>=1.1`, `pytesseract>=0.3.10`, `pillow>=10.0`.
  - The Tesseract binary, found through `TESSERACT_CMD`.
- **Known problems:**
  - No OCR end-to-end proof on Windows.
  - At most 2 columns; no `.doc` files.
  - The backend fails with `No module named 'pymupdf'` when `.v2deps` is not on PYTHONPATH.

## 2. Profile / anonymiser

- **V2 files:**
  - `agents/profile/detect.py`: rule detectors for email, phone, URL, address, name, bias proxies and the references block.
  - `agents/profile/anonymise.py`: hides every form of the name and the contacts, then runs an attacker-style leak check.
  - `agents/profile/ner.py`: optional GLiNER and resume-ner; off in V2.
  - `agents/profile/parse.py`: plain Qwen3-4B with prompt `profile-q1`, one call per chunk. Code then checks quotes, normalises dates and merges duplicates.
  - `agents/profile/prompts.py`, `scoring.py`, `agent.py`, `contracts/profile.py`.
  - `integration/qwen_retry.py`, plus the chunk-size setting `HS_V2_PROFILE_CHUNK_CHARS=800`.
- **Verdict: adapt.**
  - "Anonymise in code, then parse with an LLM against quotes" matches our design.
  - Two things must be fixed: gendered words and the injection handling.
- **Tests:**
  - `tests/test_profile_privacy.py` (40): rules, real code, no LLM.
  - `tests/test_profile_parse.py` (21): mock backend.
  - `integration/tests/test_qwen_retry.py` (4): mock.
  - Eval in `eval/profile_agent/`, on 10 **self-written** EN/FR CVs:
    - privacy: 0/65 leaks;
    - parse, with real Qwen: F1 0.90 for skills, 0.96 for experience, 1.00 for education.
- **Dependencies:** pydantic. `requirements-profile.txt` (optional, unpinned): `transformers>=4.40`, `torch>=2.2`, `gliner>=0.2.13`, tiktoken, sentencepiece, protobuf.
- **Known problems:**
  - **Gendered words are not anonymised** (verified):
    - `agents/profile/detect.py:244` defines `GENDER_WORDS = {"male", "female", "homme", "femme", "masculin", "feminin"}`.
    - These words are matched only in the header and contact region (`detect.py:315-320`).
    - Nothing handles pronouns (he/she) or gendered job titles ("Ingénieure") in running text. `agents/profile/README.md:101-102` admits this.
    - Evidence: `eval/profile_agent/results/rules/p02_fr_classic.anon.txt` still contains "Ingénieure DevOps".
    - `bias/rules.py:40` records pronouns but never flags them.
  - The agent parses skills from an injected CV line; this is only flagged (`profile:possible_prompt_injection`).
  - A 1,500-character chunk gave `finish_reason=length` and 0 items. The workaround is 800-character chunks (`docs/integration/V2_TIMEOUT_PROGRESS_FIX.md`).
  - A company that shares the candidate's surname gets hidden too.

## 3. Job Agent

- **V2 files:**
  - `agents/job/agent.py`: extract, retry once, validate.
  - `agents/job/prompts.py`: versions job-v1…v4 (NuExtract-2.0-2B) and **job-q1 (active)**, which uses plain Qwen3-4B.
  - `agents/job/backend.py`: refuses any model name containing "lora".
  - `agents/job/validate.py`, the guardrails:
    - the evidence quote must exist in the offer;
    - min_years must match the quote;
    - must/nice is corrected from cue words;
    - "Java and Spring Boot" is split into one requirement per skill;
    - more than 30% invented requirements triggers human review.
  - `agents/job/sections.py`, `scoring.py`, `contracts/job_requirements.py` + `.schema.json`.
  - Injection filter: `integration/upstream.py:110-125`.
- **Verdict: reuse as-is** (minor adapt). It already outputs must/nice with verbatim evidence and min_years. The README must be updated, since it still describes NuExtract.
- **Tests:** all mock (fake backend):
  - `tests/test_job_agent.py` (37), `test_job_contract.py` (7), `test_job_eval.py` (12), `test_job_filter.py` (5), `test_job_q1.py` (10), `test_job_v3.py` (14), `test_job_v4.py` (7).
  - Real eval in `eval/job_agent/` on 10 real USAJOBS offers. job-q1 scores: sentence F1 0.659, skill F1 0.670, strict F1 0.578, at 113 s per offer on a GTX 1650.
- **Dependencies:** pydantic; it reuses the Qwen server.
- **Known problems:**
  - An injected "PhD in physics" was accepted as a must-have. It was fixed in code (`f2c56be`), not in the prompt.
  - On a single-paragraph offer it warns "no requirement section found"; V2 treats this warning as benign.

## 4. Matcher

- **V2 files:**
  - `matcher/agent.py`.
  - `matcher/prompt.py`, prompt `p1`. The whole CV goes in a `<<< >>>` fence, then the requirement, then a knowledge block marked "terminology only".
  - `matcher/validate.py`, deterministic validator v2:
    - exact-substring quotes and spans;
    - `evidence_years`;
    - negation, certification and injection checks;
    - `review_priority`.
  - `matcher/output_adapters.py`.
  - `matcher/backends_api.py`: OpenAI-compatible client, FallbackBackend.
  - `matcher/backends.py`, `backends_extra.py`.
  - `matcher/schemas.py`, `matcher/json_schemas/`.
  - `matcher/factory.py`: builds the pipeline from env vars.
  - `matcher/pipeline.py`.
  - `config/matcher_models.json`, `config/matcher.env.example`.
- **Verdict:**
  - **Reuse** the prompt/LoRA/output contract.
  - **Adapt** the validator: go back to v1 behaviour or the post-hoc fix, and add the QA-032 duration forms.
  - **Adapt** factory: fix the Windows path bug, and split the stations out of `pipeline.py` for n8n.
- **Tests:**
  - Mock:
    - `matcher/tests/test_matcher.py` (17), `test_pipeline.py` (10), `test_agent_pipeline.py` (8), `test_matcher_integration.py` (23, stub HTTP), `test_evidence_years.py` (3), `test_weak_cues.py` (1);
    - `tests/qa/*` (~73);
    - `benchmark/tests/test_benchmark.py` (9).
  - Real, gated by `HS_LIVE=1` plus running servers:
    - `matcher/tests/test_live_matcher.py` (5);
    - `tests/live/test_live_contracts.py` (11).
  - Last recorded mock run (`docs/qa/last_run_mock.txt`): 228 passed, 5 skipped, 3 xfailed.
- **Dependencies:**
  - From `requirements-matcher.txt` (pinned): `pydantic==2.14.1`, `numpy==2.5.4`, `bm25s==0.3.13`, `psutil==7.2.2`, `pytest==9.1.1`, `torch==2.14.1`, `transformers==5.19.0`, `peft==0.21.2`, `accelerate==1.15.0`, `safetensors==0.8.0`, `tokenizers==0.23.3`, `huggingface_hub==2.2.0`, `lm-format-enforcer==0.11.3`.
  - llama-cpp-python: pinned 0.3.16 in `matcher_models.json`, but 0.3.22 (cu125) is used on Windows. It is in **no** requirements file.
- **Known problems:**
  - **Windows path bug** (verified), `matcher/factory.py:109`: `if model.startswith("/") and not Path(model).exists():`.
    - A missing `C:\...` judge checkpoint does not fall back to the default.
    - Two tests fail on Windows: `matcher/tests/test_agent_pipeline.py:175` (`test_factory_wiring_and_judge_fallback`) and `matcher/tests/test_judge_nli.py:188-189` (`test_judge_config_env_and_pins`). Both are listed in `.pytest_cache/v/cache/lastfailed`.
    - The bug is documented in `docs/integration/V2_LOCAL_GPU_VALIDATION.md:45`.
    - A related problem: `factory.py:41` hard-codes the Linux path `"/home/user/judge_runs/deberta-hs-v1/best"`.
  - **Validator v2 overfitted val** (verified), `benchmark/results/final/lora__gated/metrics.md`. Test split, 199 requirements:

    | | macro-F1 | false-MET |
    |---|---|---|
    | after validation | **0.678** | 0.131 |
    | raw model output | **0.887** | 0.178 |

    - The validator changed 18.1% of decisions, and 0.719 needed human review.
    - Cause (`docs/qa/FAILURES.md:378-385`, QA-031): duration rules were tuned on val phrasing only and moved 36 correct METs per arm to UNCERTAIN.
    - The fix was made post-hoc, after seeing test data, and brings the score to 0.862 = the v1 replay. So v2's extra rules gave no held-out gain (`docs/orchestration/FINAL_REPORT.md:27,43-45`).
  - QA-032 is still open: "Since 2018…" and "Seven years…" are not parsed. A patch exists at `docs/qa/patches/S6-QA-032-duration-forms.patch`.
  - QA-027: the LoRA reads "2019 - present" as fewer than 5 years.
  - The test run is partial: `base__gated` has 173/199 rows, so base vs LoRA was never compared on test.
  - The whole CV goes in the prompt with n_ctx 4096 (or 2048 in `RUN_LOCAL.md`), so long CVs risk overflow.
  - Benchmark data (bench-v1) is synthetic.

## 5. RAG

- **V2 files:**
  - `rag/`: retrieval.py, chunking.py, corpus.py, api.py, build_index.py, evaluate.py, plus experiments exp02/exp03 and an n8n workflow.
  - `rag/data/esco/esco_ict_skills.jsonl` (1,621 ESCO ICT concepts) and `rag/data/jobs/` (20 USAJOBS postings).
  - `matcher/knowledge.py`, with these classes:
    - `GatedKnowledge` (`rag.gated.v1`): BM25, exact label/alias first, strict cut-off, ≤ 280 characters;
    - `RagKnowledge` (legacy BM25);
    - `QdrantKnowledge`;
    - `FixtureKnowledge`.
  - `rag_opt/` (end-to-end arms).
- **Verdict: adapt.** What V2 has and lacks against our Locked RAG:
  - It has BM25, an ESCO corpus, chunking code, a Qdrant client and the "knowledge, not evidence" rule.
  - It lacks hybrid search with RRF in the live path, a reranker, ESCO graph expansion (broader/related) and the full ablation table.
  - The measured RAG gain in V2 is nil: Δ macro-F1 −0.005 on val.
- **Tests:**
  - `rag/tests/test_rag.py` (20), `test_gated_knowledge.py` (19), `test_robustness.py` (7), `test_rag_opt_scripts.py` (4): mock.
  - `rag/tests/test_real_models.py` (6): real, gated by `RAG_REAL=1`.
  - Query sets are in `rag/eval/`.
- **Dependencies:** from `rag/requirements.txt` (pinned):
  - `bm25s==0.3.13`, `numpy==2.5.4`, `pandas==3.0.6`, `tabulate`;
  - `qdrant-client==1.19.1`, `fastapi==0.143.0`, `uvicorn==0.54.0`, `httpx==0.28.1`;
  - `pytest==9.1.1`, `sentence-transformers==6.1.0`, `jsonschema==4.26.0`.
- **Known problems:**
  - **Pin conflict** (verified):
    - `rag/requirements.txt:12` pins `sentence-transformers==6.1.0`, whose metadata requires `huggingface-hub>=1.3.0,<2.0.0`.
    - `requirements-matcher.txt:14` pins `huggingface_hub==2.2.0`.
    - The two files cannot both install. The V1 venv actually holds huggingface_hub 1.33.0, so the matcher pin is not honoured.
    - No V2 doc mentions this conflict.
  - The ESCO subset covers only ICT skills.
  - Qdrant was never run locally ("no Qdrant" in `RUN_LOCAL.md`).

## 6. Bias Auditor

- **V2 files:**
  - `matcher/bias_audit.py`: `check_result` (rules_v1) and `counterfactual()`. The counterfactual prepends a name, gender, nationality or age line, re-runs the Matcher and counts flips. It also has placebo attributes.
  - `bias/auditor.py`: variants rules_v1, rules_v2, reviewer, rules_v2+reviewer.
  - `bias/rules.py`.
  - `bias/reviewer.py` + `bias/prompts/reviewer_v1.txt`.
  - `bias/flip_analysis.py`: Wilson CIs, Fisher and McNemar tests.
  - `bias/stats.py`, `bias/make_testset.py`, `bias/data/` (dev 34, test 32, holdout 44).
  - `benchmark/bias_eval.py`.
  - Wiring: `matcher/pipeline.py:107-119`.
- **Verdict: adapt.**
  - The counterfactual machinery exists and was measured, but it is **off in the live flow**. It runs only with `HS_LIVE_COUNTERFACTUAL=1`, and neither the V2 start script nor the run guide sets it.
  - Our Locked design needs it **on**, limited to must-haves and borderline cases.
- **Tests:**
  - `bias/tests/test_bias_auditor.py` (21) and `tests/qa/test_qa_bias.py` (9): mock.
  - Real batch results in `benchmark/results/bias/`:
    - rules_v2 vs v1 on the holdout: recall 19/26 for both; false positives 1/18 vs 9/18;
    - flips: base 2/253, LoRA 4/270, placebo 0;
    - McNemar p = 0.69, with low power.
- **Dependencies:** pydantic only. The optional reviewer uses the Qwen server.
- **Known problems:**
  - Not live (above).
  - Each requirement costs about 8 extra Matcher calls.
  - QA-029: a name-signal flip reproduces on borderline duration items.
  - The lexicon rules miss paraphrases.

## 7. Judge

- **V2 files:**
  - `matcher/judge.py`, NLIJudge:
    - it first checks that quotes are exact substrings;
    - MET must be entailed by its quotes;
    - MISSING/contradicted must be contradicted by its quotes;
    - MISSING/not_documented is checked against the whole CV in 1,500-character chunks;
    - it never changes a decision, it only adds flags.
  - `matcher/factory.py:33-41,99-125` holds the pins:
    - xsmall: `cross-encoder/nli-deberta-v3-xsmall@a1508764…`, τ 0.75/0.85;
    - base: `MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli@6f5cf0a2…`, τ 0.40/0.65.
  - `judge/experiment.py`, `finetune/train_judge.py`, `docs/JUDGE.md`, `benchmark/results/judge/`.
- **Verdict: reuse as-is** (structure), but **switch to the base checkpoint** or retrain.
  - On val, xsmall has AUROC 0.75 against 0.94 for base.
  - With xsmall, FAIL precision is 0.000–0.042, and the review rate rises from 0.594 to 0.901 (`docs/JUDGE.md:142-144`).
- **Tests:**
  - `matcher/tests/test_judge_nli.py` (16): mostly mock. The real xsmall test is skipped unless the model is cached.
  - `tests/qa/test_qa_judge.py` (10): mock (keyword NLI stand-in).
- **Dependencies:** `torch==2.14.1`, `transformers==5.19.0`.
- **Known problems:**
  - The Windows path bug (§4).
  - The fine-tuned judge was lost.
  - It cannot do year arithmetic.
  - It works in English only.

## 8. Report Writer

- **V2 files:**
  - `reporter/writer.py`: for each section, an SLM attempt, then the validator, one retry, then a deterministic fallback.
  - `reporter/slm.py`: Qwen3-0.6B Q8_0 in-process on CPU through llama-cpp-python, with a sha256 check.
  - `reporter/slm_prompt.py`.
  - `reporter/slm_validate.py`: closed vocabulary, numbers, quotes, no hiring verdicts.
  - `reporter/build.py`, `render.py`, `schema.py`, `measure.py`, `replay.py`.
  - `backend/reporter_adapter.py`.
- **Verdict: reuse as-is** (plus the banner fix). The validated SLM with a deterministic fallback is exactly "facts only, fact-checked". What is missing is the **tiny model vs Qwen3-0.6B benchmark** our design asks for.
- **Tests:**
  - `reporter/tests/test_fallback.py` (8), `test_render.py` (11), `test_slm_validate.py` (5): mock.
  - `reporter/tests/test_slm_real.py` (2): real Qwen3-0.6B.
- **Dependencies:** llama-cpp-python (unpinned anywhere).
- **Known problems:**
  - **The human-review banner ignores upstream flags:**
    - `reporter/render.py:56-57` (Markdown) and `:107-108` (HTML) render only from `overview.requires_human_review`.
    - That value is the per-requirement count from `matcher/pipeline.py:151` (via `reporter/build.py:123-125`).
    - Upstream reasons (reader, profile, job) are built in `integration/upstream.py:128-148` and never reach the reporter (`backend/main.py:322`).
    - The frontend works around it with a separate note (`frontend/src/App.tsx:1070-1073`, `:1088-1092`).
    - It is documented in `docs/integration/V2_INTEGRATION_REPORT.md:111-112`.
  - Only 71.6% of sections were accepted, and only 13/25 summaries.
  - p50 is 30 s per report.

## 9. Outcome

- **V2 files:**
  - `matcher/pipeline.py:65-87` (`aggregate`): human review is required whenever any reason exists.
  - `matcher/validate.py:191`: `needs_human_review = priority != "low"`.
  - `integration/upstream.py:128-149` collects these upstream reasons: `reader:low_confidence_or_ocr`, `profile:identity_leak_left`, `job_agent:possible_prompt_injection`, and others.
  - In the frontend, the status starts at "Pending review".
- **Verdict: rewrite.**
  - V2 has no confidence score and no invite/reject decision; every candidate gets a report.
  - Our Locked design needs a confidence gate in n8n (Switch/If), automatic invite or reject for clear cases, a human-approval step, rejections with reasons, and a target review rate ≤ 25%.
- **Tests:** `tests/qa/test_qa_fallback.py`, `test_qa_contracts.py`, `integration/tests/test_api_v2.py` (10), `integration/tests/test_contract.py` (4). All mock.
- **Known problems:**
  - The review rate is far above target: 0.719 on test, and 0.90 with the Judge on val. The gate barely discriminates.
  - The banner bug (§8).

## 10. Data

- **V2 files:**
  - `benchmark/data/` (bench-v1), **synthetic**, generated by `make_dataset.py` (seed 20261015) with a MANIFEST of sha256 hashes:
    - train: 150 cases, 681 requirements;
    - val: 45 cases, 202 requirements;
    - test: 45 cases, 199 requirements (locked).
  - `finetune/data/sft_*.jsonl`.
  - `bias/data/`.
  - `eval/profile_agent/`: 10 self-written CVs.
  - `eval/job_agent/`: 10 **real** USAJOBS offers with gold.
  - `rag/data/esco/`, `rag/data/jobs/` (20 USAJOBS postings).
- **Verdict: reuse as-is** for development and regression; **not enough** for our evaluation.
  - Our Locked plan needs real public data first, plus 30–50 human-labelled CV × job pairs. V2 has no real CVs.
  - `FINAL_REPORT.md`: "nothing here measures real recruiting data".
- **Licences:**
  - ESCO is EU-published; we must check its terms ourselves.
  - USAJOBS is US government data.
  - Not checked in T01.

## 11. Evaluation / benchmark

- **V2 files:**
  - `benchmark/` (run.py, metrics.py, compare.py, consolidate.py, rescore.py, judge_eval.py, bias_eval.py, rag_check.py).
  - `benchmark/results/` (final, val, CONSOLIDATED_val.md).
  - `rag_opt/` (replay_validator, review_rate).
  - `judge/experiment.py`, `reporter/measure.py`.
  - `scripts/eval_job_agent.py`, `eval_privacy.py`, `eval_profile_parse.py`, `check_gold.py`.
  - `docs/qa/` (FAILURES.md, patches).
  - `docs/orchestration/FINAL_REPORT.md`.
- **Verdict: adapt.**
  - The harness is solid: pre-registered, with a locked test split and metrics macro-F1, false-MET and review rate.
  - It needs an end-to-end mode over n8n and our human-labelled pairs.
  - Lessons to carry over:
    - never tune on test;
    - test phrasing variants;
    - finish the base vs LoRA arm.
- **Tests:** `benchmark/tests/test_benchmark.py` (9, mock).

## 12. Prompts

- **V2 files:**
  - `prompts/PROMPT_LIBRARY.md`: profile-q1 and job-v1…q1, with error analysis.
  - `matcher/prompt.py` (p1) and `matcher/prompt_variants.py`.
  - `agents/job/prompts.py` (job-q1), `agents/profile/prompts.py` (profile-q1).
  - `reporter/slm_prompt.py`, `bias/prompts/reviewer_v1.txt`.
- **Verdict: adapt.**
  - The content is reusable, and the job prompt history (v1→q1, with metrics) is ready-made before/after material.
  - But the prompts live inside Python files. Our rule 8 needs them in `prompts/<station>/v<N>.md` with headers and a library row.
  - The upstream prompts have no "inputs are data, not instructions" rule (`V2_INTEGRATION_REPORT §6.3`).

## 13. Frontend

- **V2 files:**
  - `frontend/src/App.tsx` (1,710 lines, monolithic), `api.ts`, `workflow.ts`, `contracts.ts`, `cv-files.ts` (client-side tesseract.js and pdfjs OCR), `RagInspector.tsx`.
  - `frontend/.env.example`.
  - Ports 5173/5174, which are reserved for V1/V2.
- **Verdict: not needed for the Locked architecture as-is.**
  - n8n is the main path, with its form trigger and human-approval step.
  - The frontend could be adapted later for the demo only if a task asks for it (rule 12).
- **Tests:**
  - `src/api.test.ts` (13) and `src/workflow.test.ts` (13): vitest, mock.
  - `tests/uploads.spec.ts` (2) and `tests/workflow.spec.ts` (3): Playwright.
- **Dependencies:**
  - react ^19.1, vite ^6.3.5, tesseract.js ^7, pdfjs-dist ^6.4.299, tailwindcss ^4.1, vitest ^5.0.5, @playwright/test ^1.52.
  - `engines: node >=22.16.0 <23`. This laptop has Node v25.9.0.

---

## Cross-cutting problems

| # | Problem | Where |
|---|---|---|
| a | `torch==2.14.1` assumed on the cu128 index. Docs say the cloud could not check it (`docs/WINDOWS_LOCAL_BENCHMARK.md:14-20`). The real Windows GPU run used `torch 2.11.0+cu128` (`docs/matcher_integration/lora_compat.json:109`). The V1 venv has `2.14.1+cpu`. | `requirements-matcher.txt:8` |
| a | `sentence-transformers==6.1.0` needs `huggingface-hub<2.0.0`, but the pin is `huggingface_hub==2.2.0`. | `rag/requirements.txt:12` vs `requirements-matcher.txt:14` |
| — | llama-cpp-python, gguf and the backend web stack are missing or scattered across requirements files. There are 4 requirements files and no single installable set. | all `requirements*.txt` |
| b | `startswith("/")` Windows path bug. | `matcher/factory.py:109` |
| c | Validator v2 overfit val: test macro-F1 0.678 vs raw 0.887. | `benchmark/results/final/lora__gated/metrics.md` |
| d | Gendered words not anonymised. | `agents/profile/detect.py:244,315-320` |
| e | Banner ignores upstream flags. | `reporter/render.py:56-57,107-108` |
| f | Qwen HTTP 500 on candidate 2 of a two-CV run: **cause not proven**; a 5-probe repro gave all HTTP 200. Mitigated by one retry (`integration/qwen_retry.py`), "failure recovery, not a confirmed fix". The diagnostic log `..\v2_qwen_diagnostics.log` shows `UnicodeDecodeError` tracebacks, not 500s. | `docs/integration/V2_TIMEOUT_PROGRESS_FIX.md:121-159` |
| — | Doc and script ports disagree: `V2_WINDOWS_RUN.md` §3-5 says 8081/8000/5173, `start_v2_windows.ps1` says 8082/8001/5174. Doc and code defaults disagree too: `HS_UPSTREAM_MAX_TOKENS` is 3072 in the doc and 768 in code. | `docs/integration/` |
| — | Model files live only in the **V1** repo cache (`repo\.cache\hf\hub`). | see T01 report |

## Summary

| station | verdict | effort | risk |
|---|---|---|---|
| Reader | adapt (OCR reuse; vision path + fusion new) | L | High: no VLM yet, 6 GB VRAM shared with Qwen3-4B, Tesseract not installed |
| Profile / anonymiser | adapt | M | Medium: gendered words, injection, chunking |
| Job Agent | reuse as-is (minor adapt) | S | Low |
| Matcher | reuse model + contract; adapt validator and factory | M | Medium: overfit validator, long-CV context, partial test arm |
| RAG | adapt (add dense, RRF, rerank, graph, ablation) | L | Medium: pin conflict, no measured gain so far, Qdrant never run locally |
| Bias Auditor | adapt (turn counterfactual on, scoped) | M | Medium: latency (8 extra Matcher calls per requirement) |
| Judge | reuse as-is; switch xsmall → base | S | Medium: high false-FAIL rate inflates the review rate |
| Report Writer | reuse as-is + banner fix + tiny-model benchmark | S | Low |
| Outcome | rewrite (confidence gate in n8n) | M | High: V2 review rate 0.72–0.90 vs our target ≤ 0.25 |
| Data | reuse for development; add real CVs + 30–50 labelled pairs | L | High: no real CVs, licences unchecked |
| Evaluation / benchmark | adapt | M | Medium |
| Prompts | adapt (move to `prompts/<station>/v<N>.md`) | S | Low |
| Frontend | not needed (n8n is the UI path) | — | Low |
