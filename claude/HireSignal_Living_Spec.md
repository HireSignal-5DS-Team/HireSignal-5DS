# HireSignal — Living Spec

Copy of the live doc (source of truth): https://claude.ai/artifact/YRcaKGscuMatzKM4DkCjum · refreshed Oct 18, 2026 · @Yassine

## 0. Current direction: our V3 build (2026-10-18)

We are rebuilding HireSignal in a new folder (YD) on the teammate's laptop, using the team's V2 as a read-only reference. Sections 3-8 below are the earlier plan; where they differ, this section and Decisions 9-22 win.

**Pipeline (Confirmed, Decision 10):** n8n Trigger → 1 Reader (OCR + vision, late fusion) → 2 Profile (anonymise, then parse) in parallel with 3 Job Agent → 4 Matcher + RAG → 5 Bias Auditor (swap test) → 6 Judge (NLI) → 7 Report Writer → 8 Outcome (confidence gate, n8n approval step).

| Area | Plan | Status |
| --- | --- | --- |
| Orchestration | n8n self-hosted, one node per station, error workflow | Confirmed |
| Models | All local, free cloud model as one-setting backup | Confirmed |
| Model server | llama.cpp llama-server b11139 on port 8090: one Qwen3-4B copy, LoRA scale 0 = plain, 1 = Matcher; Ollama for vision and tiny models | Confirmed (running, 3.25 GB VRAM) |
| RAG | ESCO + postings; hybrid BM25 + dense (Qdrant) + reranker + ESCO graph; retrieve only when no literal match; 2 chunkings; ablation table | Confirmed |
| Multimodality | V2 OCR path + vision path, late fusion main, early fusion compared | Confirmed |
| Outcome | Clear cases automatic; flagged or borderline to an n8n approval step; review target 25% or less | Confirmed |
| Data | Djinni English (MIT) + 40 pairs labelled by 2 humans; Kaggle Resume PDFs (CC0) for reader tests | Confirmed; labelers not chosen |
| Prompt library | Every key prompt versioned with a before/after | Confirmed |
| Way of working | Brain (this chat) plans and reviews in the folder; Claude Code builds from tasks/ files; Yassine approves; no git until the app is ready | Confirmed |

**Measured so far (real GPU, 30-item smoke test on synthetic bench-v1 val, with ESCO knowledge):** LoRA Matcher macro-F1 0.911 vs base 0.647; valid JSON 1.000 vs 0.900; about 1.2 s per requirement. Files: YD/eval/results/2026-10-18_lora_check/.

**Environment (T01-T02b done):** Python 3.12 .venv with one clean requirements set (torch 2.14.1+cu126); models copied to YD/models with a hash manifest; n8n 2.43.7 on portable Node 24 (port 5678); Tesseract not yet installed (admin install by the teammate, path in .env).

## 1. Use Case & Scope

**Project:** HireSignal, CV Screener. A company opens tech or data jobs and receives many CVs. The system reads each CV (PDF), extracts the key facts, compares them with the job requirements, checks the scoring for bias, and ranks the candidates with explanations. Clear strong matches are invited, clear weak matches are rejected, and everything in between goes to the recruiter.

| Item | Detail | Status |
| --- | --- | --- |
| Topic | HireSignal is the graded team project. Support Triage is dropped (too close to the user's other project) | Confirmed |
| Job domain | Tech and data jobs | Confirmed |
| CV language | English | Confirmed |
| Outcomes | Ranked shortlist + auto-invite for top candidates + auto-reject for clear weak matches | Confirmed |
| Borderline cases | Recruiter review queue | Assumption |
| Users | Recruiters (receive reports); candidates (receive emails) | Assumption |
| In scope | CV intake, layout-aware extraction, entity extraction, anonymisation, job matching, bias audit, ranking, invite/reject emails, review queue, logging | Assumption |
| Out of scope | Real candidates' personal data, commercial applicant-tracking integration, production hosting, full interview scheduling | Assumption |
| Data | Public or synthetic CVs only; job offers written by the team | Assumption |

## 2. Team & Roles

Team size: 5–6 (Confirmed). Names and split not decided. Roles will be set once the architecture is fixed, so each role matches a part of it.

Rule from the brief: every member must be able to explain any part of the system in the Q&A.

## 3. Platform & Tech Stack (earlier plan; see section 0)

| Item | Choice | Status |
| --- | --- | --- |
| Budget | Zero: no paid AI subscriptions or API credits. Everything must run on free tiers or free local software | Confirmed |
| Hardware (user's laptop) | NVIDIA RTX 4050 Laptop GPU with 6 GB video memory; 7.7 GB RAM. The system now runs on the teammate's laptop (32 GB RAM, RTX 4050 6 GB) | Confirmed |
| Where models run | Earlier: hybrid. Now: all local + free cloud backup (Decision 12) | Superseded |
| Which models | Station needs + model-card fact sheets + measurements (Decision 8) | Confirmed |
| Groq account | The user has a Groq account and a dedicated HireSignal API key (old keys deleted, key never put in code) | Confirmed |
| Automation platform | n8n self-hosted with npm on a portable Node 24 inside the project folder, port 5678 (Decision 7) | Confirmed |
| Data | Public CVs only. Personal details never sent to a free cloud tier | Confirmed |
| RAG stack | Earlier: sentence-transformers + ChromaDB. Now: Decision 14 (hybrid BM25 + dense in Qdrant + reranker + ESCO graph) | Superseded |
| n8n ↔ Python link | Station HTTP endpoints (port 8010) called by n8n nodes | Confirmed |
| Fine-tuning | Bonus. The team's QLoRA Matcher adapter is used (measured 0.911 vs 0.647) | Confirmed |

## 4. Architecture (earlier 8-station version; current pipeline in section 0)

**Final (Confirmed 2026-10-12): Option A, a sequential chain.** Every CV goes through the same stations in order, and each station adds its result to one shared candidate record. Stations updated 2026-10-18 by Decision 10.

1. **Trigger** (system, n8n): CV upload + job ID starts the run.
2. **Document reader** (system): turns the file into clean text + a confidence level.
3. **CV Parser** (agent): fills a fixed form: skills, degree, titles, years of experience.
4. **Anonymiser** (system, plain code): removes name, photo, contact details, age and gender words before scoring.
5. **Matcher** (agent + RAG): scores each job requirement as met / missing / uncertain, with reasons.
6. **Bias Auditor** (agent): checks the reasons and runs a name / gender swap test.
7. **Report Writer** (agent): writes the recruiter's explanation using only facts from the record.
8. **Outcome** (system, rules in n8n): invite, recruiter review, or reject.

Prototype: https://claude.ai/artifact/S6PzJiRdDuwRs7CeNj8mJC. Optional upgrade if time remains: Option B (Match split into parallel judges).

## 5. RAG Plan (earlier; current design = Decision 14)

| Item | Plan | Status |
| --- | --- | --- |
| Corpus | ESCO ICT/data subset (CC BY 4.0) + job postings (from V2's RAG work) | Confirmed |
| Why this corpus | The matching step needs to know which skills are related (e.g. PyTorch → deep learning frameworks) | Confirmed |
| Chunking comparison | One concept per chunk vs fixed size / by section for postings | Confirmed |
| Retrieval | Hybrid BM25 + dense, RRF, reranker, ESCO graph expansion, only when no literal CV match | Confirmed |
| Evaluation | Known-answer queries, MRR / hit@k, ablation BM25 → dense → hybrid → +rerank → +graph | Confirmed |

## 6. Multi-Agent Design

Pattern: sequential chain with two input paths (Confirmed, Decision 10). LLM agents: Profile parser, Job Agent, Matcher (with RAG tool), Report Writer; Bias Auditor runs the Matcher on swapped copies; Judge is an NLI encoder; Reader, Anonymiser, Validator and Outcome are code.

## 7. Multimodality Plan (current = Decision 15)

| Item | Plan | Status |
| --- | --- | --- |
| Accepted inputs | Digital PDF, scanned PDF, photo of a CV (JPG, PNG), TXT, DOCX | Confirmed |
| Counted as multimodal | Digital PDF with layout and images (scanned PDF, photo) | Confirmed |
| Method | Path 1: V2 OCR (PyMuPDF / Tesseract with image clean-up). Path 2: vision model reads the page image. Late fusion merges field by field; early fusion (image + OCR text in one input) compared | Confirmed |
| Test set | Kaggle Resume PDFs (CC0) in several forms (digital, scanned, photo) | Confirmed |

## 8. Prompt Library & Fine-Tuned Model

**Prompt library (Confirmed):** prompts/<station>/v<N>.md, never edited in place, logged in prompts/PROMPT_LIBRARY.md with role, technique, failure, fix, before/after numbers. First entry: Matcher v1 (V2 p1 baseline) and the constrained-decoding guardrail.

**Fine-tuned model (Confirmed bonus):** the team's QLoRA adapter on Qwen3-4B-Instruct-2507 for the Matcher (trained with BM25-ESCO knowledge k=3 in the prompt). Served by llama-server with per-request LoRA scale.

## 9. Decision Log

Every architecture choice is recorded here: the options, the choice, and why the others lost. This becomes the report's justification section and the team's Q&A preparation.

| # | Decision | Options | Choice | Why the others lost | Status |
| --- | --- | --- | --- | --- | --- |
| 1 | How the agents are organised | A: Sequential chain · B: Parallel scorers · C: Router · D: LLM supervisor | **A: Sequential chain.** B kept as an optional upgrade of the Match station | B: 3 judges + a combiner add calls, prompts and a weighting to justify. C: every CV needs the same steps, so nothing to route. D: path changes every run, cannot be tested or explained, fairness risk | Confirmed 2026-10-12; stations updated by Decision 10 (2026-10-18) |
| 2 | Which inputs count as multimodality | Digital PDF with layout · Scanned PDF / photo · TXT / DOCX | **Digital PDF with layout + scanned PDF / photo.** TXT / DOCX accepted but not counted | TXT and DOCX are the same modality as the rest of the project | Confirmed 2026-10-12 |
| 3 | How images are turned into text | Vision LLM · OCR · OCR + LLM cleanup | See Decision 15 | — | Superseded by 15 (2026-10-18) |
| 4 | LLM provider | Groq free · Gemini free · OpenRouter free | See Decision 12 | — | Superseded by 12 (2026-10-18) |
| 5 | Candidate record (data contract) | JSON · CSV · DB row; identity together · separate; skills plain · with evidence; years LLM · code; score LLM · code | JSON; identity separate; skills with evidence; LLM judges, code counts. Contract: claude/HireSignal_Candidate_Record.md | CSV fits lists badly; identity behind a filter is weaker; plain skills can't be checked; LLM arithmetic is unreliable | Confirmed 2026-10-12; principles carried into V3 |
| 6 | Where the models run | All cloud · all local · hybrid | Hybrid (earlier) | — | Superseded by 12 (2026-10-18) |
| 7 | How n8n is hosted | n8n Cloud · npm self-hosted · Docker | npm self-hosted, portable Node 24 LTS in the project folder | Cloud: 14-day trial then paid, can't reach localhost models. Docker: extra RAM/setup. Global Node v25 unsupported (n8n needs 20.19-24.x) | Confirmed 2026-10-18 (n8n 2.43.7, port 5678) |
| 8 | How models are chosen | Reputation · hardware fit · station needs + fact sheets + measurements | Station needs + fact sheets + measurements | Reputation or hardware fit alone give no technical "why this model" | Confirmed 2026-10-18 |
| 9 | Strategy after the team built V2 | Fix their repo · new build using V2 as reference · from scratch | **New build using V2 as reference** | Fix: n8n stays outside the core, errors stay, hard to own. Scratch: redoes measured parts, too slow | Confirmed 2026-10-18 |
| 10 | Architecture base | Our 8-station chain · V2 structure + fixes | **V2 structure + fixes** (CV path + Job Agent path, anonymise before parse, NLI Judge, plus n8n trigger, fusion Reader, swap test, Outcome gate) | Our chain assumed typed-in requirements, parsed before anonymising, no evidence check | Confirmed 2026-10-18 |
| 11 | Orchestration in n8n | One /analyze endpoint · one node per station · n8n AI Agent nodes | **One node per station** + Switch/If + error workflow | Single endpoint is a black box; AI Agent nodes make strict JSON harder | Confirmed 2026-10-18 |
| 12 | Where the models run (replaces 6) | All local · all cloud · hybrid | **All local** + free cloud backup, on the teammate's laptop | All cloud: token caps, CVs leave the machine. Hybrid: V2 showed local Qwen3-4B + LoRA works | Confirmed 2026-10-18 |
| 13 | Model server | Ollama only · llama-cpp-python · merged LoRA in Ollama · llama-server per-request LoRA | **llama-server b11139, port 8090**, one Qwen3-4B, LoRA scale 0/1; Ollama for vision and tiny models | Ollama 0.40.5 refuses LoRA; llama-cpp-python needs CUDA pip build and swaps copies; merging = 8 GB + re-test; newest llama.cpp blocked by Smart App Control | Confirmed 2026-10-18 (3.25 GB VRAM; scale 0 identical to plain 30/30) |
| 14 | RAG design | BM25 only · dense only · hybrid + rerank · + graph, retrieve-when-needed | **Hybrid + reranker + ESCO graph**, only when no literal match; 2 chunkings; ablation | BM25 only: no embedding/vector store to justify. Dense only: misses exact names. Query rewriting: extra LLM call | Confirmed 2026-10-18 |
| 15 | Multimodality (replaces 3) | OCR only · vision only · early / intermediate / late fusion | **OCR + vision, late fusion main, early fusion compared** | OCR only: no fusion. Intermediate: needs training time | Confirmed 2026-10-18 |
| 16 | Outcome | No decision · auto invite/review/reject · recommend only | **Confidence gate** + n8n approval step, review ≤25%, rejections with reasons + request review (GDPR Art. 22) | No decision: 72% to review. Recommend only: not automation enough | Confirmed 2026-10-18 |
| 17 | Bias Auditor | Rules only · swap test on | **Swap test on** (must-haves + borderline), same model; fix gendered words | Rules miss proxies anonymisation leaves | Confirmed 2026-10-18 |
| 18 | Judge | xsmall · base · drop | **NLI Judge, DeBERTa-v3-base-mnli-fever-anli** | xsmall AUROC 0.75 vs 0.94; dropping loses the only independent check | Confirmed 2026-10-18 |
| 19 | Report Writer model | Template · tiny model · Qwen3-0.6B | Benchmark tiny vs 0.6B, keep smallest passing the fact checker | Template: not an AI step | Assumption |
| 20 | Data | Synthetic only · real public | **Djinni English (MIT)** + 40 pairs labelled by 2 humans; **Kaggle Resume (CC0)** for reader tests; Vanetik if tech; bench-v1 for dev | resume-job-description-fit: no licence or source; PJB: no download | Confirmed 2026-10-18 (labelers not chosen) |
| 21 | Invalid Matcher JSON | Change prompt · constrained decoding | **Constrained decoding**, prompt unchanged | LoRA trained on the current prompt | Confirmed 2026-10-18 (T03 measures) |
| 22 | Way of working | Copy-paste relay · Brain reads the laptop folder + Claude Code builds · GitHub only | **Brain plans/reviews in YD (V2 read-only); Claude Code builds one tasks/ file at a time; Yassine approves; no git until the app is ready** | Relay slow/lossy; GitHub sees only pushed code | Confirmed 2026-10-18 |

## Deliverables & Milestones Tracker

**Final deliverables (supervisors' email, Confirmed 2026-10-12)**, due 2 days before the validation session, via Blackboard:

- The project: exported n8n workflow JSON or a repository link, with clear install and run instructions.
- Technical report, max 8 pages excluding annexes: tools, LLM, RAG, agent architecture, evaluation, security.
- Prompt library as an annex of the report.
- A PowerPoint presentation.
- A demo video, max 5 minutes.

**Validation session:** 20 minutes presentation + live demo, 10 minutes questions. Every member speaks and must answer on any part. Date: not recorded yet.

Grading (original brief): Prompt engineering 20% · RAG 25% · Multi-agent 25% · Multimodality 15% · Demo/report/Q&A 15%. Fine-tuning is a bonus.

## Open Questions

- [ ] Who are the 2 labelers for the 40 real CV x job pairs (about 2-3 hours each)?
- [ ] Who does which work package (team or AI tools)?
- [ ] Validation session date (deliverables are due 2 days before it)
- [ ] Tesseract admin install on the teammate's laptop
- [ ] Vision model for the Reader's second path (chosen by measurement)
- [ ] Report Writer: tiny model vs Qwen3-0.6B benchmark
- [ ] Outcome thresholds (score cut-offs, borderline band) to reach a review rate of 25% or less
- [ ] Vanetik dataset: are its 5 vacancies tech jobs? (T03 checks)

**Roadmap (V3, 2026-10-18):** T01 repo + inventory: done. T02/T02b environment, models, llama-server, n8n, LoRA check: done. **T03 next:** JSON-schema decoding + full val run + real data download + labelling kit. Then: station endpoints reused from V2 (Reader, Profile, Job, Matcher) → first n8n end-to-end run → RAG upgrade (hybrid + rerank + graph, ablation) → fusion Reader → Bias swap test + Judge base → Report Writer benchmark → Outcome gate + approval step → evaluation on the 40 labelled pairs → security tests → report, prompt library, PowerPoint, demo video, then push the whole folder to GitHub.

## Change Log

| Date | Change | Why |
| --- | --- | --- |
| 2026-09-22 | Spec doc created | Starting Week 1 planning |
| 2026-10-01 | Added Support Triage specification | Shortlisted topic at the time |
| 2026-10-12 | Topic switched to HireSignal; Decision Log added; Decisions 1, 2, 5, 6 confirmed; 7, 8 proposed; zero budget; free-provider research; work moved into a Claude Project; deliverables from the supervisors' email; spec updated only at session end | See the live doc for the detailed 2026-10-12 rows |
| 2026-10-13 | Teacher's freedom rule recorded; explainer docs created; work-division options proposed | Teacher: any tool or model is allowed, but every choice needs a technical reason |
| 2026-10-17 | Reviewed the team's V2 build | Strong engineering, but n8n only wraps RAG, no outcome, synthetic data only, 24 unmerged branches, no slides or video |
| 2026-10-18 | New direction: V3 rebuild in folder YD using V2 as reference; Decisions 9-22 added; 3, 4, 6 superseded; 7, 8 confirmed; section 0, Open Questions and Roadmap rewritten | V2 missed mandatory requirements; rebuilding on their best parts is faster than fixing their design |
| 2026-10-18 | Built T01-T02b: repo, environment, models, n8n, llama-server; LoRA check 0.911 vs 0.647; git paused until the app is ready | Ollama refused LoRA adapters, so llama-server serves one Qwen3-4B with per-request LoRA; user asked to finish locally before pushing |
