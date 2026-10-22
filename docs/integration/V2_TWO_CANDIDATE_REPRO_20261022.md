# HireSignal V2 — two fictional PDF CVs, local RTX 4050 (2026-10-22)

## Scope and branch isolation

- Branch: `feature/agent-integration`; **not** `main` or either V1 release branch.
- Windows real services: FastAPI port 8001, React port 5174, dual-model
  llama.cpp Qwen3-4B port 8082.
- Baseline V1 services and branches were not modified.
- Original user report: a V2 two-CV run failed with HTTP 502 because plain
  upstream Qwen server had returned HTTP 500 during a Profile Agent step after
  a successful first candidate.
- The current V2 branch already contains a **bounded one-time retry** for
  upstream Qwen HTTP 500/502/503 (`integration/qwen_retry.py`, commit
  `0593d6a`), plus Windows startup fixes. There was no new model or Matcher
  change in the current diagnostic session.

## Controlled model-swap probe

Real CUDA-capable Qwen3-4B server (8 layers offloaded) received five sequential
chat-completion requests:

| Step | HTTP | Elapsed | Result |
|---|---:|---:|---|
| Plain Qwen: Profile synthetic CV 1 | 200 | 32.2 s | JSON response, finish=stop |
| Plain Qwen: Profile synthetic CV 2 | 200 | 25.4 s | JSON response, finish=stop |
| Switch to Qwen + LoRA | 200 | 5.8 s | Short completion |
| Switch back to plain Qwen | 200 | 30.0 s | JSON response, finish=stop |
| Plain Qwen: short Job Agent example | 200 | 8.2 s | JSON response, finish=stop |

**Interpretation:** Model swapping is functional in this test. The original
HTTP 500 was **not reproduced** and may be intermittent. This does not prove
the server can never fail under load.

## Two-candidate app reproduction

Both PDF files and the job description were **entirely fictional synthetic
examples**. The tests used the actual `/api/v2/analyze` API, real Reader,
Profile, Job, LoRA Matcher with RAG, Bias, Judge and SLM report, sequentially
on the same dual-model Qwen server. Safe summary artifacts were stored
**outside the worktrees** in `C:\Users\semah\HireSignal-Integration\diagnostics`.

| Stage | Candidate 1 | Candidate 2 |
|---|---:|---:|
| HTTP | **200** | **200** |
| Reader | OK (0.01 s) | OK (0.00 s) |
| Profile | OK (71.30 s) | OK (74.87 s) |
| Job Agent | OK (38.83 s) | OK (38.10 s) |
| Matcher pipeline | OK (30.48 s) | OK (28.35 s) |
| Reporter | OK (27.14 s) | OK (112.79 s) |
| Total per candidate | **168.6 s** | **248.6 s** |
| Profile incomplete | No | No |
| Requirements | 5 | 5 |

Decisions:
- Candidate 1: 2 MET, 2 UNCERTAIN, 1 MISSING.
- Candidate 2: 0 MET, 5 MISSING.

The results are a **functional demonstration**, not a matching-accuracy score.
The `job_agent:validation_warnings` review reason was present for both;
the review requirement must not be silently omitted in the UI.

## Why the SQL result needs caution

A follow-up end-to-end API run of the synthetic second PDF also succeeded:
**HTTP 200 in 180.5 s**, with real agent/provenance and no transient retry
during Profile or Job. The CV Reader extracted two occurrences of SQL from
the PDF; Profile extracted SQL with the exact evidence
`Wrote SQL queries to retrieve sales records`.

The Job Agent, however, produced a **compound requirement**:
`Candidates must have SQL skills, with at least 2 years of professional
experience building AI or machine learning models`.

The fictional second candidate has SQL but **not** 2 years of ML experience,
so a MISSING verdict on that compound requirement does not show the Matcher
failed to read SQL. It shows that Job Agent requirement atomization is
inadequate for per-skill explanations. Proper evaluation should split
`SQL` and `2 years of ML experience` into independently grounded
requirements. This remains **an open quality improvement**, not an automatic
hiring decision. Do not modify the measured upstream prompt or V1 Matcher
blindly or claim this benchmark is a pass for matching accuracy.

## Automated validation

- Backend: **37 tests passed** in
  `integration/tests/test_qwen_retry.py`,
  `integration/tests/test_upstream.py` and
  `integration/tests/test_api_v2.py`.
- Frontend: **30 tests passed**; lint and production build passed.
- The original HTTP 500 was **not reproduced** during the controlled
  tests, so the exact prior internal llama.cpp exception remains unknown.
- The bounded 5xx retry path is tested, but longer real-world runs could still
  fail. GPU model memory, server logs and schema-based extraction remain
  necessary for production-like QA.
