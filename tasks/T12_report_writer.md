# T12 — Report Writer agent (station 7)

Read `CLAUDE.md` first. **Start only after T11b is finished and reported.**

Approver decision (Yassine, 2026-10-18): the Report Writer is an LLM agent on **Qwen3-4B plain**, the copy already loaded in llama-server with LoRA scale 0, so it needs no extra GPU memory. A **code fact checker** guards it, and a **template** is the fallback. A short Qwen3-0.6B comparison is allowed, **time-boxed to 15 min** (skip it and say so if it runs over). This replaces the "tiny vs 0.6B" plan of Decision 19.

## What the agent does
- **Input:** the anonymised decision record of one CV × job pair, the same data `/outcome` and `/bias` use:
  - requirements (kind, text, decision, verified quotes, Judge verdict);
  - score, gate outcome and reasons;
  - Reader flags (mode, image-quality reasons);
  - bias flags and the swap result.
  - **Never** identity data or raw CV text beyond the verified quotes.
- **Output** (JSON-schema constrained decoding):
  - `recruiter_summary`: 3–6 plain sentences on why this outcome;
  - `requirements`: one short line per requirement (met / missing / uncertain + its quote or "not found in CV");
  - `candidate_letter`: for invite or reject only. A reject letter gives the missing must-haves as reasons and the right to request human review (GDPR Art. 22). Never mention bias or Reader internals to the candidate.
  - `flags_for_recruiter`: image quality, swap flip, low confidence, in plain words.
- **Rule "LLM writes, code checks."** The text may only state facts that are in the record.

## Fact checker (code, `services/report/checker.py`)
- Every quoted CV text must be an exact substring of a verified quote in the record.
- Every requirement mentioned must exist, with the same decision.
- Numbers (score, years) must equal the record.
- The outcome word must equal the gate outcome.
- No names or identity words: re-use the bias lexicon + the anonymiser placeholders.
- No requirement may be invented, and no must-have may be silently dropped.
- **On failure:** retry once with the checker's error list added to the prompt. If it fails again → fall back to the **template** (`services/report/template.py`), with the info flag `report:template_fallback`.

## Prompt library
`prompts/report_writer/v0.md` (naive) → `v1.md` (facts-only rules, schema, examples). Add rows to `PROMPT_LIBRARY.md` with the dev before/after numbers: fact-check pass rate and invented facts per report.

## Evaluation (choose on dev, report on test once)
- Setups:
  1. **template** (baseline);
  2. **Qwen3-4B plain + v1** (main);
  3. optionally **Qwen3-0.6B** (`models/Qwen3-0.6B-Q8_0.gguf`, served through Ollama or a temporary llama-server; record the port and stop it after), **max 15 min**.
- Measures:
  - fact-check pass rate on the first try and after the retry;
  - template-fallback rate;
  - invented facts (the checker's error count);
  - must-haves covered;
  - length;
  - latency per report;
  - peak VRAM.
- Also hand-read 5 dev reports (an invite, a reject, a review, a photo case with a Reader flag, a bias-flag case) and paste 2 good + 1 failure example in the report, anonymised.

## Production + n8n
- `POST /report` (contracts in `services/contracts.py`). Default model = Qwen3-4B plain (env `REPORT_MODEL`, `REPORT_FALLBACK=template`).
- n8n: a **"Report Writer"** node after the gate decision and before the Switch. The recruiter Wait-form shows `recruiter_summary` + `requirements` + `flags_for_recruiter`, and the invite/reject outbox letters use the checked `candidate_letter`.
- Tests:
  - the checker catches an invented quote, a wrong decision, a wrong score and a name;
  - retry → template fallback;
  - the schema;
  - the n8n contract.
- `pytest -q` must pass.
- One real e2e run per outcome type, if time allows (invite, reject, review), saved in `eval/results/<date>_n8n_e2e_report/`.

## Report
- `tasks/T12_report.md`: plain words first; the table of setups; the chosen setup and why; examples; problems.
- `docs/REPORT_WRITER.md`, reusable in the final report.
- Stop llama-server, the API and Ollama at the end. No git.

**Time priority if short:** checker + template → 4B agent → n8n node → evaluation → the 0.6B comparison (drop it first).
