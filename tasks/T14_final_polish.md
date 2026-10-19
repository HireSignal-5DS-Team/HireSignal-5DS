# T14 — Final polish: injection sanitising, figures, submission check, push preparation

Read `CLAUDE.md` first. Approver answers to the T13 questions (Yassine, 2026-10-19):
1. **Reduce the injection risk:** remove detected injection sentences from the CV text **before the Matcher** (and before the Report Writer), and still send the case to review. Do not refuse the CV.
2. **Accept** the webhook token stored in n8n's local execution data (local, pruned after 14 days). Document it in `docs/SECURITY_REPORT.md`; keep execution saving on.

## Part A — Injection sanitising
- The injection detector already finds the sentences (`injection.injected_sentences`). Remove exactly those sentences from the text that `/match` and `/report` see. Keep the original for the recruiter view, with the removed sentences listed.
- Add the info flag `profile:injection_removed`. The review reason (gate rule 0) stays.
- Quotes must still be verified against the **sanitised** text. A quote taken from a removed sentence is never valid.
- **Re-run A1** (4 pairs × 4 attacks) and report before → after: requirement decisions changed vs the clean CV (T13: 8/16 attacks, 11 decisions). Target: as close to 0 as possible. Also check the 52 gold CVs: 0 sentences removed (no false positives), so the final evaluation numbers are unchanged.
- Tests. `pytest -q` must pass.

## Part B — Figures for the report and slides (`docs/figures/`, PNG + SVG, readable in black and white)
Make each figure from the real result files (no typed numbers), with a script `scripts/make_figures.py`:
1. **Pipeline diagram:** the n8n chain, stations, models, and where the human steps are.
2. **RAG retrieval:** dev/test MRR@10 for BM25, dense (3 embedders), hybrid, + rerank, + graph (checked golds).
3. **Multimodal:** CER by setup (OCR / vision / late / early) and by condition (close photo / hard photo / scan).
4. **Bias:** requirement flips with vs without protection (T11), and identical-input share per family (T10 anonymiser vs T11b).
5. **Final outcome confusion matrix** (test) + review rate + false invites / rejects.
6. **Report Writer:** pass / fallback by prompt version (v0 → v3) and 4B vs 0.6B.
7. **Gate variants** (T08b, dev): false invites / review rate / false rejects for a–f.
8. **Latency per station** (final evaluation).

Add `docs/figures/README.md` listing each figure, its source folder and a one-line caption.

## Part C — Submission check
- Export the final n8n workflows (`n8n/*.json`, cleaned, no credentials or token values).
- Check that `README.md`, `INSTALL.md`, `demo/README.md`, `docs/FINAL_EVAL.md`, `docs/SECURITY_REPORT.md`, `docs/MULTIMODAL_REPORT.md`, `docs/BIAS_REPORT.md`, `docs/REPORT_WRITER.md`, `rag/RAG_REPORT.md` and `prompts/PROMPT_LIBRARY.md` agree on the final numbers (one source: FINAL_EVAL §3). Fix any mismatch.
- Add a short `docs/SUBMISSION.md`: what the graders get (the repo / n8n JSON, the install guide, the report, the prompt annex, the slides, the video) and where each lives.

## Part D — Push to GitHub (after the checks)
- Check `.gitignore`: `.env`, `private/`, `models/` (except `MANIFEST.md`), `tools/`, `.venv/`, caches, `data/raw/djinni/`, `data/raw/kaggle_resume/`, n8n runtime data (`.n8n/` database and logs), and `eval/outbox/` if it holds letters with personal data. Keep the small, licence-compatible data needed to reproduce the results (gold labels, processed CVs under MIT/CC0 with their NOTICE, scans, ESCO subset with its licence).
- **Secret scan:** search everything that would be committed for the token, keys, `.env` values, and identity values. The result must be 0.
- **Size check:** no file over 50 MB and a total size estimate. List what is excluded and how to get it back (`scripts/download_models.py`, the LoRA conversion steps in INSTALL.md).
- Write `docs/PUSH_CHECKLIST.md` with the results.
- **Push (Approver approved, 2026-10-19), only if the secret scan = 0 and no file is over 50 MB:**
  - remote `origin` = `https://github.com/yassinemaazaoui114-git/HireSignal.git` (the Approver's own repo; keep it **private** until submission);
  - one clean commit of the whole project, branch `main` (with the attribution lines from your instructions), then `git push -u origin main`;
  - **authentication:** if git asks for credentials, stop and ask the Approver to sign in himself (browser / Git Credential Manager). Never write a token into any file, config or log. Do not use the laptop owner's GitHub account;
  - after the push, list the files on the remote (`git ls-files | wc -l`) and confirm `.env`, `private/` and `models/*.gguf` are not tracked.
- This lifts rule 11 ("no git") **for this push only**; ask again before any later push.

## Report
- `tasks/T14_report.md`: plain words first; Part A before/after; the list of figures; the mismatches fixed; the push checklist result.
- Stop llama-server, the API and Ollama at the end.

**Time priority:** A → B → D → C.
