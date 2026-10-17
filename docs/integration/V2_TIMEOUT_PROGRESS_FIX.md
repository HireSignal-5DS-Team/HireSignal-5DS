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
