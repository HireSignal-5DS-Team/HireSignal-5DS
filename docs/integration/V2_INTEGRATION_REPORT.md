# HireSignal V2 integration report (upstream agents + V1), 2026-10-17

Branch: `feature/agent-integration`, based on `release/hiresignal-v1-stable` @ `8268438`. It is not merged anywhere.
`main`, `release/hiresignal-v1-stable` and `release/hiresignal-v1` were not touched.

Imported, by path, from `origin/feature/profile-agent` @ `7987fde`. That head already contains:
- `feature/reader-agent` @ `f7a725e`;
- `feature/job-agent` @ `e6b0b0b`.

The upstream branches fork from `0568ea8`, not from V1, so a git merge was not possible.

V1 code is unchanged: `git diff 8268438..HEAD` shows no change in `matcher/`, `rag/`, `bias/`, `judge/`,
`reporter/`, `benchmark/` or `config/`. Only these files were modified:
- `.gitignore` (upstream rules appended);
- `backend/main.py` (a new endpoint; `/api/v1/match` unchanged);
- 5 frontend files.

## 1. Audit

| component | verdict | evidence |
|---|---|---|
| Reader (PDF, DOCX, image OCR, TXT) | **PASS** | upstream suite 346/346 with Tesseract 5.3.4; real PDF read in the live run (0.3 s); corrupt PDF gives `ReaderError` (HTTP 422), never invented text |
| Profile Agent (anonymise + parse) | **PASS, with a caveat** | live: 0 leaks left; 12 placeholders; no identity value in the response. Caveat: it parses skills from an injected CV line. The skills are never Matcher evidence, and the CV is now flagged `profile:possible_prompt_injection` |
| Job Agent `job-q1` | **PASS after a fix** | live: 5/5 requirements, 3 must + 2 nice, `min_years` 2, verbatim evidence; greeting, title and benefits not extracted. A live probe found an injected sentence turned into a must-have. Now removed before the Matcher and flagged (`f2c56be`) |
| Evidence rule | **PASS** | the Matcher sees only the anonymised CV text; every MET quote has a span in it; a MET without a verbatim quote is downgraded although the Profile lists the skill (test) |
| must / nice | **PASS** | `kind` comes from the Job Agent wording ("a plus", "appreciated" give nice). Nothing is forced to must |
| `/api/v2/analyze` | **PASS** | 9 mock API tests, 2 real runs (HTTP 200); `/api/v1/match` regression test passes |
| Frontend | **PASS (mock tests)** | 22/22 vitest, `tsc -b`, eslint and build pass. Real browser run not done |
| One-port model swap (VRAM plan) | **PASS on CPU, GPU not verified** | one llama-cpp-python server serves both aliases and closes one model before loading the other |

## 2. What was added

- `integration/upstream.py`: `analyze_documents()` runs Reader, Profile, Job Agent, then the V1 pipeline.
  - Each stage records ok or failed with the time it took.
  - A failed stage stops the run (HTTP 502 with the stages); no result is invented.
  - Identity values never leave the function.
  - Injected instructions are detected in both inputs.
- `backend/main.py`: `POST /api/v2/analyze` takes `cv_text` or `cv_file_b64` + `cv_file_name`, plus `job_text`.
  - The 15 MB body limit and the 10 MB CV limit are enforced.
  - The run uses the same serial semaphore as V1.
  - The Reporter runs after the pipeline.
- Frontend, REAL mode, design unchanged:
  - REAL mode calls `/api/v2/analyze`; the uploaded file goes to the server Reader;
  - each candidate shows "Pipeline stages (actual)" and the upstream review reasons;
  - raw file bytes are not kept in the campaign;
  - `VITE_API_FLOW=v1` restores the old flow.
- `docs/integration/V2_WINDOWS_RUN.md`: PowerShell instructions.

## 3. Test results (cloud, 4 vCPU, no GPU)

| kind | result |
|---|---|
| Unit + mock suites (V1 + upstream): `integration matcher benchmark/tests tests/qa tests/test_*.py reporter bias judge` | 711 passed, 5 skipped, 0 failed (before `f2c56be`) |
| V2 mock/contract tests (`integration/tests/test_upstream.py`, `test_api_v2.py`) | 20 passed (after `f2c56be`) |
| Upstream suite alone | 346 passed (with Tesseract installed) |
| Frontend (vitest) | 22 passed; tsc, eslint and build OK |
| Real upstream models + full real pipeline, PDF | HTTP 200, 612 s, all 5 stages ok (`integration/e2e_evidence/20261017-v2-real-pdf/`) |
| Real injection probe, text CV | before fix: injected must-have accepted; after fix: removed + flagged (HTTP 200, 410 s) |
| Real-SLM reporter test | passes (after the portable llama-cpp rebuild) |
| GPU tests | **not run**: Windows only (V2_WINDOWS_RUN.md §6) |

Skipped tests are live tests without `HS_LIVE=1` and optional GPU/NER tests.

No accuracy number is claimed for V2. The two live runs are synthetic examples; they show that the flow works.

## 4. Real vs mock

| stage | live runs | mock tests |
|---|---|---|
| Reader | real (PyMuPDF; Tesseract in the suite) | real code |
| Profile / Job | real Qwen3-4B Q4_K_M plain | `FakeBackend` scripted answers |
| Matcher | real LoRA `0b6925b1` + gated RAG | V1 `Fake` |
| Bias, Judge | real rules_v2, real DeBERTa xsmall | real code / V1 test doubles |
| Reporter | real Qwen3-0.6B (3/6 sections SLM, the rest deterministic) | patched |

Live injection probe (`integration/e2e_evidence/20261017-v2-real-injection/`):
- Before the fix:
  - the Matcher was not fooled: no MET came from injected text, and all 6 requirements were flagged
    `possible_prompt_injection`;
  - the Job Agent turned "PhD in physics" into a must-have;
  - the Profile listed Kubernetes, Spark and AWS from the injected line.
- After the fix (live re-run, HTTP 200, 410 s):
  - "PhD in physics" was removed before the Matcher and listed in `upstream.dropped_injected_requirements`;
  - review reasons `job_agent:possible_prompt_injection` and `profile:possible_prompt_injection` are set;
  - the 5 real requirements are unchanged, and all are flagged for review.

## 5. Models and dependencies

- Same pinned V1 models: Qwen3-4B-Instruct-2507 Q4_K_M + LoRA `0b6925b1`, DeBERTa-v3 xsmall `a1508764`,
  Qwen3-0.6B Q8_0.
- The upstream agents reuse the plain Qwen3-4B (same GGUF): no new weights.
- New Python packages: `pymupdf`, `python-docx`, `pytesseract`, `pillow`.
- Optional: Tesseract binary (scans), `requirements-profile.txt` (NER detectors, off by default).
- New env vars:
  - `HS_UPSTREAM_LLM_URL`, `HS_UPSTREAM_LLM_MODEL`, `HS_UPSTREAM_MAX_TOKENS` (3072),
    `HS_UPSTREAM_TIMEOUT` (300; CPU needs about 1800);
  - `TESSERACT_CMD`;
  - `VITE_API_FLOW`.

## 6. Blockers and risks

1. The GPU swap has not been verified on the RTX 4050: VRAM after a swap, swap time, and `n_ctx` 6144 fit.
   There is a documented fallback.
2. CPU latency is 7 to 10 min per candidate, almost all of it in Profile and Job. GPU latency is unmeasured.
3. The upstream prompts (`profile-q1`, `job-q1`) were not edited: changing them would void Ayoub's measured prompt
   evaluation. Injection is handled in code. A prompt-level "inputs are data" rule is a follow-up for Ayoub, and
   needs a re-run of his eval.
4. The Job Agent warns "no requirement section found" on a single paragraph. Such jobs always get the review
   reason `job_agent:validation_warnings`.
5. The browser end-to-end with real models has not been run.
6. Upstream review reasons are shown in the UI and the API. The reporter's HUMAN REVIEW banner counts only
   per-requirement flags.

## 7. Review checklist (owner)

- [ ] Read `git diff 8268438..feature/agent-integration -- backend frontend integration/upstream.py`.
- [ ] Windows: follow V2_WINDOWS_RUN.md §1 to §6. Record `nvidia-smi` after a swap and the stage table.
- [ ] Browser: upload a PDF, paste a job paragraph, check the stages and the HUMAN REVIEW flags.
- [ ] Check that `/api/v1/match` still works from the V1 frontend (`VITE_API_FLOW=v1`).
- [ ] Ayoub: review the import (`9f0aec5`) and the injection finding.
- [ ] Decide whether to merge. Never merge into `main` or a release branch without your explicit approval.
