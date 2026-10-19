# HireSignal (our version) — rules for Claude Code

Read this file fully before every task. It is the contract between the team roles.
Project context (decisions and why): `claude/HireSignal_Living_Spec.md` and `claude/HireSignal_Handoff.md`. Read them when a task needs background; never edit them (the Brain maintains them).

## Roles
- **Brain** (Claude, web chat): plans, writes tasks in `tasks/`, reviews your work by reading this folder directly, explains it to the team.
- **Developer** (you, Claude Code in VS Code): implement exactly one task file at a time, run things on this Windows laptop (RTX 4050 6 GB, 32 GB RAM), commit.
- **Approver** (Yassine): approves every step.

How a task works: the approver tells you "Do tasks/Txx_*.md". You do it, then write `tasks/Txx_report.md` (format at the end). If something in a task is unclear, contradicts this file, or seems wrong, STOP and write the question in the report instead of guessing. Never change a "Locked" decision below; propose changes in the report.

## The project
HireSignal: an AI CV screener for tech/data jobs (English CVs), Advanced Deep Learning final project (ESPRIT 5DS). The topic is not graded; the engineering choices are. Every choice needs a technical reason we can defend in the Q&A.

Mandatory exam requirements (from the brief):
1. **Automation platform:** the pipeline runs on n8n, triggerable end-to-end (not run manually cell by cell).
2. **Prompt engineering (core of the grade):** versioned prompt library; for each prompt: role, technique, failure cases observed, fix; at least one before/after iteration per key prompt.
3. **RAG:** our own knowledge base; justify corpus, chunking (size/overlap), embedding model, vector store, retrieval setup (top-k, filters, reranking); retrieval evaluation on test queries; comparing two chunking strategies is strongly valued.
4. **Multimodality** and 5. **Agentic AI** (agents with clear roles).
Deliverables: n8n workflow JSON + repo with install/run instructions, technical report (max 8 pages), prompt library annex, PowerPoint, demo video (max 5 min).

## Locked architecture (sequential chain, two input paths)
```
n8n Trigger (CV file + job text)
  -> 1 Reader        : OCR path + vision-model path, LATE FUSION (early fusion compared)
  -> 2 Profile       : anonymise (code) THEN parse (LLM)          || 3 Job Agent: job text -> must/nice requirements
  -> 4 Matcher + RAG : per requirement MET / MISSING / UNCERTAIN with verbatim CV quotes
  -> 5 Bias Auditor  : counterfactual swap test ON (must-haves + borderline), rules
  -> 6 Judge         : NLI check that quotes support each decision
  -> 7 Report Writer : small model, facts only, fact-checked
  -> 8 Outcome       : confidence gate in n8n: clear cases automatic (invite / reject),
                       flagged or borderline -> n8n human-approval step; target review rate <= 25%;
                       rejections carry reasons + "request human review"
```
- **Orchestration (Locked):** n8n self-hosted, one n8n node per station (each station is a small HTTP endpoint or an LLM call), Switch/If nodes for the outcome, an n8n error workflow. No single black-box `/analyze` endpoint as the main path.
- **Models (Locked principle, exact choice measured later):** local first (Qwen3-4B family, the team's Matcher LoRA as first Matcher, DeBERTa NLI judge); a free cloud model as backup, switchable by an env setting through an OpenAI-compatible API. Report Writer: benchmark a tiny model vs Qwen3-0.6B.
- **RAG (Locked):** ESCO (+ job postings) knowledge base; hybrid search (BM25 + dense embeddings in Qdrant, merged with RRF) + reranker + ESCO graph expansion (broader/related skills); retrieve only when a requirement has no literal match in the CV; two chunking strategies compared; ablation table BM25 -> dense -> hybrid -> +rerank -> +graph. RAG output is KNOWLEDGE, never EVIDENCE.
- **Data (Locked):** real public data first (licences checked), synthetic only as backup; 30-50 CV x job pairs labelled by humans for the end-to-end evaluation.

## Hard rules
1. Budget zero: free and local software only. Never add a paid service.
2. "The LLM judges, code counts": LLMs give judgements (statuses, dates, quotes); code computes years, scores, thresholds.
3. A MET decision needs a verbatim CV quote that code verifies (exact substring + position). No quote, no MET.
4. Identity (name, contacts, photo) is stored apart (git-ignored `private/`) and never reaches the Matcher.
5. Secrets: never print, log or commit keys. Use `.env` (git-ignored) and keep `config/.env.example` with placeholders.
6. **Reference code (team V2) is READ-ONLY:** `C:\Users\semah\HireSignal-Integration\v2-agent-integration`. Never modify it, never run git commands that change it. When you reuse code, copy it into this repo and put at the top: `# Adapted from team V2: <relative path> (feature/agent-integration @ a5a03ff)`, then adapt it.
7. Do not touch the V1 repo (`C:\Users\semah\HireSignal-Integration\repo`) or the ports used by V1/V2: 5173, 5174, 8000, 8001, 8081, 8082. Our ports: n8n 5678, station API 8010, llama-server 8090 (main Qwen3-4B + LoRA server, see T02b), Ollama 11434 (vision and tiny models later). Change only if busy, and report it.
7b. Model files are COPIED into our git-ignored `models/` folder (never loaded from the V1 repo cache). Tools we install for this project (portable Node, n8n data) live in git-ignored `tools/` and `.n8n/` inside this folder; do not change global system settings (global Node, PATH) without asking in the report.
8. Prompts: every prompt lives in `prompts/<station>/v<N>.md` with a header (role, technique, date, change vs previous version). Never edit an old version: create a new one and log it in `prompts/PROMPT_LIBRARY.md`.
9. Evidence: never write "works", "fixed", "accurate" without a test or a measured result. Label results as mock / real-CPU / real-GPU. Save experiment results in `eval/results/<date>_<name>/` with the config used.
10. One Python environment (`.venv`, Python 3.12) and one dependency set that installs cleanly. No hard-coded user paths in code; use config/env.
11. **No git for now.** Do not run any git command (no commit, add, branch, push) until the Approver says so. We finish the app locally first, then push the whole folder once. Track progress in the task reports instead.
12. Keep it simple: no feature that is not in a task.

## Report format (`tasks/Txx_report.md`)
1. Done (bullet list, with file paths)
2. Evidence (commands run + key output, test results)
3. Not done / problems
4. Questions for the Brain
5. Suggested next step
