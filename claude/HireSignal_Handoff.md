# HireSignal — Handoff for the next conversation

Last updated: 2026-10-18 (end of session). Read this first, then `HireSignal_Living_Spec.md` (section 0 + Decisions 9-22). Together they replace the earlier conversation.

## How to start a new chat

Paste this as the first message:

> Read `claude/HireSignal_Handoff.md`, then `HireSignal_Living_Spec.md` (section 0 and Decisions 9-22). Then continue from "Next step" in the handoff.

## Working rules (from the user)

1. Start every new chat with the reminder in Arabic: **اعقد نيتك**.
2. Concise answers, simple language, no over-explaining. Explain technical details while working (the user wants to learn each part: RAG, prompt library, etc.).
3. Update the living spec only once, at the end of each session ("end of session"), then refresh the project copy. Confirmed/Assumption flags, dated Change Log rows, Open Questions.
4. For every decision: options in simple words, honest recommendation, the user chooses, record the choice and why the others lost.
5. Lock the plan before working: the user says "start".
6. Ask when unclear. Be honest when an idea is weak.
7. Budget zero: free and local only.
8. Every model/tool choice needs a technical reason (teacher's rule), not "we studied it".

## Live links

- Living spec (source of truth): https://claude.ai/artifact/YRcaKGscuMatzKM4DkCjum
- Old architecture walkthrough (8-station prototype): https://claude.ai/artifact/S6PzJiRdDuwRs7CeNj8mJC

## What happened (Oct 17-18)

- The team built their own "V2" (repo HireSignal-5DS, branch feature/agent-integration @ a5a03ff): Reader → Profile (anonymise + parse, Qwen3-4B) ‖ Job Agent → Matcher (Qwen3-4B + team QLoRA) with BM25-ESCO RAG → Validator → rules Bias Auditor → DeBERTa NLI Judge → Qwen3-0.6B Report Writer, React + FastAPI. Strong engineering, but: n8n only wraps RAG (mandatory requirement 1 not met), no outcome (72% to review), synthetic data only, prompt library only for 2 prompts, 24 unmerged branches, no PPT/video, 255/270 commits by AI.
- Decision: rebuild our own V3 (Decisions 9-22), using V2 as read-only reference.

## How we work now (Decision 22)

- **This chat = Brain.** It is linked to the teammate's laptop (device `laptop-l5eh7h6v`, Windows user `semah`) through the Claude desktop app. Granted folders: `C:\Users\semah\Desktop\YD` (our build, read/write) and `C:\Users\semah\HireSignal-Integration\v2-agent-integration` (V2, read-only). The device shell is a Linux VM: it reads/edits files but cannot run the Windows GPU models or reach localhost services. If the device tools are missing, the laptop is offline or the chat is not linked: ask the user to open this chat in the desktop app on that laptop.
- **Claude Code (VS Code, teammate's account) = Developer.** It reads `YD/CLAUDE.md` (rules) and does one `YD/tasks/Txx_*.md` at a time, then writes `tasks/Txx_report.md`. The Brain writes task files directly into YD and reviews reports and result files there.
- **Yassine = Approver.** He pastes one line into Claude Code, e.g. `Read CLAUDE.md, then do tasks/T03_json_val_data.md`.
- **No git** until the app is ready to show (CLAUDE.md rule 11).

## Environment on the laptop (done)

- 32 GB RAM, RTX 4050 6 GB, i7-13650HX, Windows 11; 41 GB free disk.
- `YD/.venv` Python 3.12, one frozen `requirements.txt` (75 packages, torch 2.14.1+cu126, CUDA works).
- `YD/models/` with MANIFEST.md (hashes): Qwen3-4B Q4_K_M GGUF, Matcher LoRA f16 GGUF, Qwen3-0.6B Q8_0, DeBERTa xsmall + base (MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli).
- **llama-server** (llama.cpp b11139, `tools/llama.cpp/`, `scripts/start_llm.ps1`) on port 8090: one Qwen3-4B with the LoRA, per-request scale 0 = plain, 1 = Matcher; default scale forced to 0 at startup (b11139 ignores --lora-init-without-apply). 3.25 GB VRAM.
- Ollama 0.40.5 (port 11434) kept for later vision / tiny models; it refuses LoRA adapters.
- n8n 2.43.7 on portable Node 24 (`tools/node`, `tools/n8n`, data in `.n8n/`), `scripts/start_n8n.ps1`, port 5678; owner account apparently created.
- Tesseract: NOT installed yet (teammate runs the UB Mannheim installer as admin, no PATH change; `TESSERACT_CMD` already in `.env`).
- Ports: ours 5678, 8010 (station API), 8090, 11434. Never touch V1/V2 ports 5173, 5174, 8000, 8001, 8081, 8082.
- At session end, Claude Code was asked to stop llama-server and n8n.

## Results so far

- LoRA check (30 bench-v1 val items, real GPU, same inputs as V2, ESCO knowledge in prompt): LoRA macro-F1 0.911, valid JSON 1.000, 1.15 s/req; base 0.647, valid JSON 0.900 (base copies the label template "MET|MISSING|UNCERTAIN"). Without knowledge: LoRA 0.880, base 0.618. Smoke test, not a benchmark. Files: `YD/eval/results/2026-10-18_lora_check/`. V2's own "0.908 on full val" could not be traced to its files.
- `docs/REUSE_INVENTORY.md` lists, per station, what to reuse/adapt/rewrite from V2 and the known V2 bugs.

## Data (Decision 20)

- Djinni English candidate profiles (~210K, MIT) + job descriptions (MIT): main real data; we label 40 pairs (4 jobs × 10 CVs) with 2 humans.
- Kaggle Resume Dataset snehaanbhawal (CC0, confirmed by the user on Kaggle): real PDF layouts for reader and scan tests.
- Vanetik vacancy-resume dataset (GitHub, GPL-3.0, human rankings): only if its jobs are tech.
- Rejected: cnamuangtoun/resume-job-description-fit (no licence, no source). PJB benchmark: no download found.
- ESCO (CC BY 4.0) is the RAG knowledge base (already in V2's rag/).

## Next step

1. **T03 is written but not started:** `YD/tasks/T03_json_val_data.md` (JSON-schema constrained decoding + full 202-requirement val run base vs LoRA; download Djinni + Kaggle + check Vanetik; data card; labelling kit for 40 pairs). User pastes: `Read CLAUDE.md, then do tasks/T03_json_val_data.md`. Then review `tasks/T03_report.md` and the result files.
2. **Ask the user:** who are the 2 labelers? Who does which package? Defence date?
3. **After T03, planned order:** T04 station endpoints on port 8010 reused from V2 (Reader, Profile, Job, Matcher) → T05 first n8n end-to-end workflow (walking skeleton) → RAG upgrade (hybrid + rerank + graph, ablation, 2 chunkings) → fusion Reader (vision model via Ollama) → Bias swap test + Judge base → Report Writer benchmark → Outcome gate + n8n approval node → evaluation on the 40 labelled pairs → security tests → report, prompt library, PowerPoint, demo video → push to GitHub.

## Things already settled, don't reopen unless asked

- Topic HireSignal; Support Triage dropped; don't copy or mention the user's other project (CallVerse).
- Sequential chain (Decision 1), now with two input paths (Decision 10).
- Outcome = confidence gate, not "no decision" (Decision 16): the user rejected recommend-only as "not automation".
- Don't change Windows security settings; don't change global Node or PATH.
- The Matcher prompt stays as V2 p1 (the LoRA was trained on it); Matcher prompt iterations come from failures on real data.
