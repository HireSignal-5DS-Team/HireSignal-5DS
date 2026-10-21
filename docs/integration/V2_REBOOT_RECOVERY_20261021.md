# HireSignal V2 — Windows reboot recovery and Qwen 500 investigation

Date: 2026-10-21. Target: `feature/agent-integration`, never V1.

## Previously recovered end-to-end results (2026-10-17)

The preserved **synthetic** two-candidate integration test was completed with all five
stages real. Artifacts are local (not committed) under
`C:\Users\semah\HireSignal-Integration\diagnostics\`:

| Test | HTTP | Elapsed | Reader | Profile | Job | Matcher | Reporter |
|---|---:|---:|---|---|---|---|---|
| Synthetic strong-match PDF | 200 | 168.6s | OK | OK | OK | OK | OK |
| Synthetic partial-match PDF | 200 | 248.6s | OK | OK | OK | OK | OK |

These are functional results, **not** hiring accuracy or RAG recall benchmarks.
The strong-match CV still received two UNCERTAIN decisions; never label it
automatically suitable without inspecting the evidence and human-review flags.

## Root-cause investigation

An earlier two-CV run failed in the Profile Agent with an upstream Qwen HTTP
**500 Internal Server Error** after one candidate had completed. A previous
failure was an upstream model response timeout, also in Profile, but the two
must not be conflated.

The V2-only `ResilientQwenChatClient` added in commit `0593d6a` retries
HTTP 500/502/503 **at most once**, with a two-second pause. It does *not*
retry malformed output, context-length rejections, 4xx responses or timeouts,
and does not silently claim success if both attempts fail. Its unit tests
cover transient, persistent and non-transient failure conditions.

Five real, consecutive, synthetic Qwen model calls were executed locally
through port 8082:

1. Plain Qwen Profile CV1 — HTTP 200, 32.2s.
2. Plain Qwen Profile CV2 — HTTP 200, 25.4s.
3. Swap to Qwen+LoRA — HTTP 200, 5.8s.
4. Switch back to plain Qwen Profile CV1 — HTTP 200, 30.0s.
5. Plain Qwen job extraction — HTTP 200, 8.2s.

This rules out **universal** failure on switching models, but does not prove
the original intermittent 500 can never recur. The exact original server
stack trace was not retained in the rebooted process. Keep retry bounded
and watch for repeated 500s.

## Windows application-control observation

During the first post-reboot test attempt, Windows Code Integrity event
3077/3033 denied loading Pillow's `_imaging.cp312-win_amd64.pyd` from the
isolated `.v2deps` directory, citing the enterprise signing policy.
This was **not** caused by Qwen. We did not disable or bypass any Windows
security controls.

A subsequent fresh Python process imported `PIL.Image`, `pymupdf`,
`docx`, `pytesseract`, `agents.reader`, `agents.profile`,
`agents.job` and `reportlab` successfully. All **173** targeted
backend tests passed afterward. If Windows blocks these modules again, check
Event Viewer → Applications and Services Logs → Microsoft → Windows →
CodeIntegrity → Operational, and use an approved/signed package or
administrator-approved exception rather than disabling security.

## Safer one-command startup

The V2 starter `scripts/start_v2_windows.ps1` was improved to:
- Default to `-NGpuLayers 8` (the tested, low-VRAM setting used while V1
  is preserved), rather than defaulting to an unverified 35 layers.
- Allow V2 to start while a separate V1 model server remains active;
  if another server runs, refuse **more than 8** V2 GPU layers.
- Set `HF_HUB_OFFLINE=1` for backend startup to avoid unplanned downloads.
- Allow **300 seconds** for a cold `/ready` response (Judge/RAG/model
  initialization previously exceeded the old 30-second cutoff).

The startup remains on independent V2 ports: 8082 for the Qwen aliases,
8001 for FastAPI, and 5174 for Vite; V1 source code and ports are unchanged.

Use this PowerShell command from the V2 repo root:

```powershell
.\scripts\start_v2_windows.ps1
```

Then use http://127.0.0.1:5174/analysis.

## Verification summary

- Backend suite (upstream/API/retry/Profile): **173 passed**.
- Frontend: **30 tests passed**, lint and build passed.
- `GET /health`, `GET /ready`, `GET /v1/models` and frontend URL all
  reported healthy after reboot.
- Historical two-synthetic-CV real-model pipeline: **2/2 HTTP 200**.
- Do not assert a permanent fix for all possible Qwen 500s or all PDFs.


## Fresh post-reboot real-model PDF smoke (2026-10-21)

After restarting the isolated V2 services, a brand-new HTTP analysis of a
**fictional searchable PDF CV** and paragraph-style job description completed
with **HTTP 200 in 119.08 seconds**, without changing any model implementation:

| Verified stage | Status | Elapsed |
|---|---|---:|
| Reader | OK | 0.29s |
| Profile Agent | OK | 39.60s |
| Job Agent | OK | 33.89s |
| Matcher pipeline | OK | 28.75s |
| SLM Reporter | OK | 16.41s |

The four resulting requirements were 3 `MET` mandatory and 1 `MISSING`
preferred, each requiring human review. The Job Agent surfaced a validation
warning and the user should inspect it. This does not establish extraction
accuracy or suitability for real-world hiring decisions.

Local JSON evidence: `C:\Users\semah\HireSignal-Integration\v2_smoke_result.json`
(not committed; synthetic inputs). No third-party data or secret was pushed.

## Additional startup checks

- The Windows PowerShell starter now passes script-parser syntax validation,
  reuses already-running V2 services safely, and prints the correct V2 link.
- Fresh backend unit run: **173 tests passed**.
- Frontend: **30 tests passed**, ESLint and production build passed.
- The Windows Code Integrity denial observed briefly during initial loading
  did not reproduce during later imports or the successful PDF test.
  No operating-system security setting was changed.
