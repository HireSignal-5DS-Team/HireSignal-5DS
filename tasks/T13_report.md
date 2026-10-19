# T13 report — Report Writer fixes, security tests, final evaluation, install guide

## In plain words
- **The report checker now catches the two misleading cases from T12:**
  - a requirement line that contradicts its own decision;
  - a reject letter that gives nice-to-haves or met items as reasons.

  A recruiter's reject after review now also gets a generated, checked letter. It worked end to end; that test case
  fell back to the template letter.
- **Final test.** The full app ran end to end through n8n on all 26 test pairs plus the 5 photo/scan cases.
  - No candidate was wrongly invited. 4 of 26 were rejected where people wanted a review (the known weak point: the
    Matcher does not express doubt). 15% went to a person.
  - A text CV takes about 1 minute, a phone photo about 3.
  - No identity was found anywhere the app writes.
- **Security.** We attacked the system: hidden or visible instructions in CVs, photos and job posts; bad files; leaks.
  - Every attack ended in "review by a person", never in an automatic decision.
  - **But the injected text does sway the Matcher** in half of the cases: the detector and the code gate are what
    stop it.
  - Four holes were found and fixed:
    - an injection flag that did not block;
    - attack phrases the detector missed;
    - no guard against invented praise;
    - a CV word ("gitlab-ci") masked as a web link.
  - Hardening added: page, image-size, language and body-size limits, and a secret token on the n8n webhook.
- **Install.** INSTALL.md, one-command start/stop scripts, a README, a demo pack and a licence list are ready. They
  were tested on this laptop, not on a clean machine.

## Part 0 — Report Writer fixes
- **Checker** (`services/report/checker.py`):
  - each line must start with Met / Missing / Uncertain and not contradict it; checked without quotes and requirement
    texts, so a quote saying "not found" cannot trigger it;
  - a reject letter may name only missing must-haves (for a human reject, also unclear must-haves), and must not call a
    human decision automated;
  - plus the **praise rule** from A1.
- **Template** lines now start with the decision word. Human invite / reject letters added. The template still passes
  the checker on all 168 record variants (gate, human reject, human invite).
- **Prompt v3** (`prompts/report_writer/v3.md`) = v2 + both rules + the human-decision rules. **Chosen on dev,
  production default** (`services/report/writer.py`, `config/.env.example`).
- **Human decision.**
  - `ReportIn.decided_by` (gate | human); human-reject records in `data/processed/report_records/<split>_human/`.
  - In n8n: Decided by human → **Report Writer (human decision)** → **Human letter** → Outbox letter.

| setup (T13 checker) | split | pass, first try | after retry | template fallback |
|---|---|---|---|---|
| v2 before the new rules (T12) | dev | 27/28 | 27/28 | 1/28 |
| v2 with the new rules | dev | 21/28 | 22/28 | 6/28 |
| **v3** | dev | **22/28** | **23/28** | **5/28** |
| v2 / **v3** | dev, human rejects (4) | 1/4 / **3/4** | 3/4 / 3/4 | 1/4 / 1/4 |
| **v3** | **test (once)** | **21/28** | **22/28** | 6/28 |
| **v3** | **test, human rejects (once)** | 1/6 | 2/6 | **4/6** |

- The new rules caught 7/27 of v2's passing dev reports: 14 letter errors and 4 contradicting lines.
- **e2e review → human reject** (`eval/results/2026-10-19_n8n_e2e_human_reject/`):
  - P32 (execution 57), the form submitted with "reject";
  - the LLM letter named met items twice, so the checked template letter went to `eval/outbox/reject/57_*.json`;
  - no "automated" wording, no GDPR sentence.
- Tests: `tests/test_report.py` (29): the line rule and its quote exemption, letter reasons (nice / met), human letter
  rules, `decided_by` on the API, the n8n human path.

## Part B — Final evaluation (`docs/FINAL_EVAL.md`, `eval/results/2026-10-19_final_eval/`)

**Test pairs** (26 pairs, 182 requirements):

| measure | result |
|---|---|
| requirements | accuracy 0.753, **macro-F1 0.644** (MET 0.771 / MISSING 0.870 / UNCERTAIN 0.291), false MET 13 |
| outcomes | agreement 21/26, **0 false invites**, **4 false rejects** (gold review), **review rate 15.4%** |
| Report Writer | 20/26 LLM, 6 template |
| bias swap | ran on 22 pairs, 22 identical inputs, **0 flips** |
| latency per CV | mean **55 s**, max 162 s (cold start) |

Station means: Profile 25.8 s, Match 10.7 s, Report Writer 13.7 s, RAG 4.6 s (117 s once, cold).

**Photo / scan cases** (5):

| measure | result |
|---|---|
| requirements | macro-F1 0.570 |
| outcomes | 2/5 = gold; 2 safe reviews of gold invites; 1 false reject (P43, same as its digital PDF) |
| latency per CV | mean 188 s (Reader 128 s) |

- The test numbers are identical to T09 V6 / T10 Part D: the chain is deterministic.
- The **component summary table** (baseline → final, with source folders) and the honest limits list are in
  FINAL_EVAL §3–4.

## Part C — Install + run
- **`INSTALL.md`** (Windows, from zero):
  - prerequisites, venv + requirements, Tesseract, Ollama + qwen2.5vl:3b, llama.cpp b11139;
  - models: `scripts/download_models.py` downloads the pinned revisions and `--verify` checks sha256 (**23/23 OK**);
    the LoRA conversion steps;
  - portable Node 24 + n8n 2.43.7, `.env`, the workflow import, start / stop, health checks.
- **`scripts/start_all.ps1` / `stop_all.ps1`.** Order: Ollama → llama-server → API (waits `/ready`) → n8n (waits
  `/healthz`).
  - Tested: all four came up healthy.
  - When called from this agent tool, the call did not return. Started processes keep the parent's handles, as already
    seen with `start_stack.ps1`. In a normal console it returns.
- **`README.md`**: overview, architecture, how to run, where the results and docs live.
- **`demo/`**: invite PDF (P50), reject PDF (L01 = P02), phone photo (K01 = P15), their job texts + confirmed cards,
  the exact `curl.exe` commands with the token header (`demo/README.md`). The same three cases were run end to end in
  T12/T13.
- **Not tested on a clean machine:** the downloads, `npm install`, the Tesseract / Ollama installers and the LoRA
  conversion. Listed at the end of INSTALL.md.

## Part A — Security (`docs/SECURITY_REPORT.md`, `tests/security/` 25 tests, `eval/results/2026-10-19_security/`)
- **A1 CV injection** (real runs, 4 pairs × visible / hidden PDF text / text inside a photo / Report Writer):
  - detected 16/16, review 16/16, injected quote used 0/16, praise 0/16;
  - **8/16 attacks still changed Matcher decisions** (11 decisions, 7 towards MET), so the safety comes from the
    detector + gate rule 0 + quote verification.
  - Fixes:
    - the injection flags `profile:` / `job_agent:possible_prompt_injection` are now in gate rule 0 (before, an
      injected CV could be auto-decided);
    - 4 new detector patterns (0 hits on the 52 real CVs / job posts);
    - the praise rule in the fact checker.
- **A2 job injection:** detected, flagged for review, the same 7 requirements as the clean post (none invented or
  deleted).
- **A3 bad files:** all give a clear 4xx error or a review flag, never a 5xx.
  - New limits: `MAX_PDF_PAGES = 10`, `MAX_IMAGE_PIXELS = 40 M`, `MAX_JSON_BYTES = 2 MB` (413).
  - New review reason `reader:non_english_text`.
- **A4 privacy:**
  - unit test: identity never in a prompt or an API response;
  - real n8n run with a synthetic identity: 11 values stored apart, **0 of 9 values in 46 places** (execution data,
    reply, logs, outbox);
  - full scan of everything written: no real identity (the 22 stored values are older false detections or the
    synthetic one);
  - fixed during the final run: "gitlab-ci" masked as a handle. P52 was re-run: same decisions, identity 0/0.
- **A5 exposure:**
  - all four services bind to 127.0.0.1;
  - **webhook token**: a "Check token" IF node + "Refuse (403)", `WEBHOOK_TOKEN` in `.env`. No header → 403, wrong
    token → 403;
  - invalid JSON 422, oversized 413;
  - known: n8n stores the token in its local execution data (accepted, documented).
- **A6 supply chain:** models 23/23 sha256 OK; `pip check` clean; `docs/LICENSES.md` (PyMuPDF AGPL-3.0, n8n
  Sustainable Use License noted).

## Part D — Prompt library annex
- `prompts/PROMPT_LIBRARY.md` was rebuilt as an annex:
  - an overview table per station;
  - one section per station with file, version, technique, failure, fix and before/after;
  - a separate table for the code guards;
  - a "Not done" note.
- All 13 prompt files kept, including the new v3; 18 rows.

## Other changes
- The n8n workflow now has 37 nodes: the token check, the human-decision letter, and `decided_by` in the gate's
  Report Writer body. It was imported, published, re-exported and cleaned.
- The `/report` contract has `decided_by`.
- Full tests: `pytest -q` → **497 passed, 1 skipped** (the Chroma store test).

## Not done / problems
- **The Matcher can be swayed by injected text.** Without the detector, injected CVs would change decisions. The
  detector is pattern-based: a creative injection could pass it. This is the main residual security risk.
- **Human-reject letters on test fall back to the template in 4/6 cases.** The model keeps naming nice-to-haves or met
  items; the template letter is correct, but plain.
- **The final evaluation ran before the "gitlab-ci" label fix.** Only P52 (test) and P31 (dev) change. P52 was re-run
  (same result), and the tables keep the as-run numbers.
- **`start_all.ps1` from the agent tool** does not return (handle inheritance); it is fine in a console.
- **No clean-machine install test** (see INSTALL.md).
- **Profile and Job prompts** still have no measured v2 (annex "Not done").

## Questions for the Brain
1. Should the residual injection risk be reduced further? For example, a second Matcher pass on a CV with injected
   sentences removed, or simply refusing CVs with a detected injection. Today the gate sends them to review, which
   already covers the detected ones.
2. Accept the n8n-stored webhook token (local, pruned after 14 days), or turn off saving successful executions? Turning
   it off would lose the e2e evidence and timings.

## Suggested next step
The report, slides and demo video from `docs/FINAL_EVAL.md` and the other docs; then the push the Approver decides.
