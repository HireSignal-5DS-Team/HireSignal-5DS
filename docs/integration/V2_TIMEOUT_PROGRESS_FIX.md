# V2 — 10-minute timeout diagnosis and progress fix (2026-10-17)

## Observed failure

A recruiter started REAL V2 analysis with two CVs. Chrome DevTools recorded
`POST /api/v2/analyze` as **(canceled)** after **10 minutes**, and the page showed
"The backend request timed out. Please retry."

The frontend instantiated `new ApiClient(undefined, 600_000)`: its AbortController
canceled the request **after 600 seconds per candidate**, even while the backend
continued communicating with Qwen. At least one historical request also returned
HTTP 502, so the timeout was **not** the only possible failure.

The Profile Agent calls Qwen **once per CV section/chunk** and may retry invalid
JSON. Long CVs therefore take substantially longer than the 128-second,
short-synthetic-PDF baseline. The single GPU server uses partial 8-layer
offloading to keep yesterday's V1 available. Neither test establishes guaranteed
throughput for large real CVs.

## Narrowly scoped V2 fix

- Retain the original synchronous `POST /api/v2/analyze` endpoint and old V1 API.
- Set **V2-only** frontend request safety timeout to **1,800 seconds (30 minutes)**;
  leave V1 at 600 seconds. This is a guard, *not* a performance improvement.
- Optional `progress_id` (UUIDv4) in the V2 request.
- Backend records metadata-only agent progress with a thread-safe in-memory store:
  `reader`, `profile`, `job_agent`, `matcher_pipeline`, `reporter`.
- `GET /api/v2/progress/{progress_id}` exposes status and elapsed time.
  It never persists CV content, job descriptions or report bodies.
- Frontend polls this endpoint every approximately 1.8 seconds while POST runs.
  It shows Reader/Profile/Job/Matcher/Reporter as *Running* or *Completed*
  **only when backend events confirm the state**. RAG, Bias and Judge remain
  unverified until the completed match response contains their actual results.
- With multiple CVs, the screen identifies the current candidate (1/N, 2/N, ...).
- If an agent fails, show failed stage metadata and the genuine API error.

## Known remaining limitations

- Startup may block polling temporarily while the Judge and knowledge base load.
- Stage updates are **polling**, not streaming token-level inference.
- If a browser tab is closed or a request expires at 30 minutes, the backend
  can continue processing without a recoverable response; durable background jobs,
  cancellation and resumable results would require additional API design.
- CVs with many sections can still be slow; run one short synthetic CV first.
- No changes to the Matcher, RAG, Judge, Bias, SLM, Qwen model weights, or V1 branches.
- Local synthetic tests are functional checks, not extraction-accuracy benchmarks.

## Commands

In the V2 worktree, using the isolated upstream dependency path:

`python -m pytest -q integration/tests/test_upstream.py integration/tests/test_api_v2.py`

In `frontend/`:

`npm test -- --run && npm run lint && npm run build`

V2 local URL: http://127.0.0.1:5174/analysis


## Follow-up: Profile Agent 502 after ~942 seconds (2026-10-17)

The original frontend cancellation was fixed, but a later **HTTP 502** occurred
while the Profile Agent parsed a much longer CV. The browser recorded:
`profile failed: BackendError: Cannot reach Qwen at http://127.0.0.1:8082/v1 (timed out)`.
The llama.cpp server was alive. Its inference log showed:
- **2,047 generated tokens**, hitting the configured **2,048-token cap**;
- only **8.41 output tokens/sec** on the partial-GPU local server;
- **314.66 seconds** of total generation time;
- client HTTP timeout **300 seconds**.

The result: an oversized or runaway JSON generation can exceed the per-call
timeout. Multiple chunks/retries make a single Profile Agent stage much longer.

Remediation within V2 integration only:
- `HS_UPSTREAM_MAX_TOKENS=768` and `HS_UPSTREAM_TIMEOUT=180`. Also set
  these as the V2 adapter's defaults, and update the Windows run guide.
- Real synthetic Profile Qwen inference with 768 tokens: **32.3 sec,
  238 completion tokens, finish_reason=stop**, valid JSON containing 5 skills,
  1 education, 1 experience.
- Real synthetic Job Qwen inference with 768 tokens: **37.1 sec**,
  6 validated requirements (4 must, 2 nice).
- Do **not** silently represent truncated Profile extraction as fully reliable.
  The V2 orchestration marks `extraction_incomplete=true` and adds
  `profile:partial_extraction_requires_review` when the parser reports
  truncated or unreadable model responses. The existing Matcher remains
  evidence-grounded on the anonymised source CV text.
- Experiment: 20 vs 8 layers offloaded to the RTX 4050 made the Profile
  sample slightly **slower** (34 vs 32 sec), so the existing **8-layer**
  GPU configuration was restored to protect V1.
- These steps constrain model calls and improve failure visibility, but
  **cannot guarantee** that a very long CV will finish quickly or that
  every 768-token response is complete. Do not claim extraction accuracy
  from synthetic smoke tests.


### V2-specific CV chunk size — verified follow-up

A synthetic 1,454-character CV with education, experience and skills was passed
as **one 1,469-character model prompt chunk** under Ayoub's original
`CHUNK_CHARS=1500`. With 768 output tokens, the model reached
`finish_reason=length` on two attempts and neither returned valid JSON.
The pipeline finished in 373 seconds (HTTP 200) but the Profile Agent produced
**0 skills/0 education/0 experience**, correctly flagged as partial.

Only for the V2 integration, `HS_V2_PROFILE_CHUNK_CHARS` now defaults to
**800**. The direct Profile Agent API and its default chunk size **1500**
remain unchanged; the integration supplies the smaller size through a new,
optional `chunk_chars` argument. No prompts, Matcher, Judge or RAG
implementations changed.

The same synthetic long CV was split into model chunks of **256, 578, and
631 characters**. Real plain Qwen3-4B inference at 768 output tokens completed
in **199 seconds**, returning **25 grounded skill entries, 2 education entries,
2 experience entries, zero parser warnings and zero detected identity leaks**.
This direct-Profile test measures extraction functionality for a synthetic
example, not general accuracy. The model still needs time proportional to
the number of CV chunks; long production CVs may require human review.


## Follow-up: intermittent upstream Qwen HTTP 500 on second CV

A two-CV browser analysis returned `profile failed: BackendError: Qwen server error 500:
Internal Server Error` on candidate 2. The historical llama.cpp traceback was not
available after the PC shutdown. The exact trigger is therefore **not proven**.

The local model server uses a dual-alias configuration on port 8082. Profile and
Job use plain `Qwen/Qwen3-4B-Instruct-2507`; Matcher uses the LoRA alias.
The server swaps between them rather than keeping both in GPU memory.

Reproduction on 2026-10-17:
- Five real inference probes (plain, plain, LoRA, plain, Job) all returned HTTP
  200, including plain→LoRA→plain switching. No universal switching bug found.
- Repeated the application's sequential flow using two short **synthetic PDF
  CVs**, the AI Engineer job description, and real Reader, Profile, Job, LoRA
  Matcher+RAG, Bias, Judge and Reporter on the local RTX 4050:
  - Candidate 1: HTTP 200, 168.6s, all five top-level stages `ok`
  - Candidate 2: HTTP 200, 248.6s, all five top-level stages `ok`
- Candidate 2 had five `MISSING` results; this is not evidence of screening
  accuracy, only confirmation that the model did not invent MET decisions.
- During these controlled runs, the newly captured llama.cpp log contained
  successful HTTP 200 completions and no Qwen HTTP 500. Some Windows logging
  callbacks emitted UnicodeDecodeError warnings, which did not break inference.

Hardening (V2 only, no changes to Ayoub's prompts/model implementations):
- The `integration.qwen_retry.ResilientQwenChatClient` wraps the existing
  `QwenChatClient` with **one** retry and a **2-second wait** only for
  `Qwen server error 500`, `502` or `503` responses.
- All 4xx, inference timeouts, schema failures and persistent 5xx errors
  continue failing honestly, without a fabricated result.
- `profile` and `job_agent` stage metadata expose the count of successful
  retry attempts through `transient_server_retries`.
- Mocked tests verify that a one-time HTTP 500 recovers and a persistent
  HTTP 500 still returns HTTP 502 from the V2 backend.
- Tests: 173 Python tests passed across integration and Profile, 30 frontend
  tests passed, ESLint and production build passed.
- This is **failure recovery**, not a confirmed fix for a specific llama.cpp
  defect, and does not guarantee that the original failing CV will succeed.
  Examine a retained server traceback if HTTP 500 recurs.
