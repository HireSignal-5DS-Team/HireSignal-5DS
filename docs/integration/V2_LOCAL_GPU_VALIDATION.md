# HireSignal V2 — local Windows RTX 4050 validation (2026-10-17)

## Isolation and provenance

- Git branch: `feature/agent-integration`, based on `bb45f3d` before local follow-up fixes.
- Stable V1 worktree: `C:\Users\semah\HireSignal-Integration\repo` (`release/hiresignal-v1`); **unchanged**.
- V2 worktree: `C:\Users\semah\HireSignal-Integration\v2-agent-integration`.
- V1 services retained: frontend **5173**, backend **8000**, LoRA server **8081**.
- V2 uses independent services: frontend **5174**, backend **8001**, GPU dual-model server **8082**.
- All CVs exercised below are synthetic; local artifacts and model weights are not committed.

## Hardware and GPU switching

- Hardware: NVIDIA RTX 4050 Laptop GPU, 6 GiB VRAM, Windows 11, Python 3.12.
- Existing cached Qwen3-4B Q4_K_M base and the pinned LoRA adapter are reused.
- V2 model server runs `llama_cpp.server --config_file` with two aliases on port 8082:
  - `Qwen/Qwen3-4B-Instruct-2507` (upstream Profile + Job)
  - `Qwen/Qwen3-4B-Instruct-2507+lora` (Matcher)
- **Non-disruptive concurrent-V1 configuration:** `n_gpu_layers=8`, `n_ctx=4096` for both aliases. This is *not* the 35-layer standalone setup in the original Windows guide.
- Actual requests switched LoRA -> plain -> LoRA. Both chat completions returned `OK` with the correct model ID, each in approximately **8 seconds**.
- Reported VRAM usage around **1259 MiB before**, **1243 MiB after plain**, **1271 MiB after LoRA** on this measurement. Under Windows/WDDM this is a point-in-time reading, not guaranteed full physical allocation.
- Original V1 alias remained available on 8081. Full 35-layer V2 GPU swapping **has not been tested** while V1 is running.

## Real PDF + paragraph job API smoke

- Endpoint: `POST http://127.0.0.1:8001/api/v2/analyze`
- Input: generated one-page synthetic PDF, natural-language job paragraph.
- **HTTP 200, total 128.38 seconds**:
  - Reader: `ok` — 0.58s
  - Profile: `ok` — 31.52s
  - Job Agent: `ok` — 25.71s
  - Matcher pipeline including RAG/Bias/Judge: `ok` — 24.84s
  - Report Writer: `ok` — 15.34s
- Requirement decisions: **3 MET must-have, 1 MISSING nice-to-have**. Every requirement was marked for human review by the V1 per-requirement pipeline.
- Privacy report: **0 identity leaks**, two identity placeholders inserted.
- Reporter: **5/5 SLM sections accepted**, 0 deterministic fallbacks for this sample; not an accuracy or reliability estimate.
- The local result initially contained the benign Job Agent warning `no requirement section found, the whole offer was used`; the V2 integration layer was corrected to **keep this warning visible but not treat it alone as a human-review trigger**.

## Regressions and UI

- Python upstream/API contracts: **21 passed** after follow-up fixes.
- Frontend Vitest: **22 passed**; TypeScript build, ESLint and production Vite build all pass.
- Browser: headless Google Chrome rendered `/analysis`, uploaded the synthetic PDF and submitted the REAL V2 form. The browser observed **HTTP 200** from the genuine `/api/v2/analyze`, reached the completed processing state and navigated to `/results`; **no JavaScript page errors**.
- Separately, a headless Chrome UI rendering test reused the **saved genuine API response as a fixture** (no second inference). It confirmed the candidates list, detail navigation, **`Pipeline stages (actual)` panel and `Validated Report Writer` panel** all render, and review text is visible. Fixture-backed UI rendering is not counted as a new real-model run.
- Expanded legacy matcher tests expose at least two **pre-existing Windows-only failures** in `matcher.factory.judge_config`: missing local `C:\\...` paths are not recognized because the fallback check uses `model.startswith('/')`. These files are **unchanged** from stable V1. The 21 focused V2 tests do pass; do not claim the entire legacy suite passes locally.
- New CORS permission permits localhost/127.0.0.1 frontend **5174** on the isolated V2 backend.
- The V2 REAL frontend now instructs users to paste a **full job paragraph**, not one requirement per line.
- The report screen explicitly states upstream review reasons in addition to per-requirement review counts.

## Current limits and reproducibility

- Local Tesseract CLI was not installed during this test; the generated PDF was text-based, **not an OCR proof**.
- DOCX and scanned-image CV browser end-to-end tests were not run.
- No automatic hiring decisions are authorized.
- V2-specific Python dependencies were installed into an isolated, Git-ignored `.v2deps/` directory and loaded through `PYTHONPATH`, preserving the V1 virtual environment.
- The local dual-model JSON config, smoke test script, synthetic CV, model weights and generated JSON outputs are outside both Git worktrees.
- All results above are functional smoke tests, **not an accuracy benchmark**.
