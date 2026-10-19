# T12 report — Report Writer agent (station 7)

## In plain words
- **What it does.** After the decision, the plain Qwen3-4B (the copy already loaded, no extra GPU memory) writes a
  short explanation for the recruiter, one line per requirement, the letter to the candidate, and the warnings.
- **How it is checked.** A code checker then reads every report. Each requirement must be there with the right
  decision, every quote must be an exact CV quote, every number must come from the record, there may be no names, a
  reject letter must give the reasons and the right to a human review, and nothing technical may be told to the
  candidate.
- **If it fails.** The model gets one second try with the list of mistakes. If that also fails, a fixed template
  writes the report instead.
- **Result.** On the test set, 25 of 28 reports are written by the model and pass the checker. The other 3 use the
  template, because the model changed a CV quote.
- **The small 0.6B model** is not good enough: 25 of 28 of its reports would fall back to the template.

## 1. Done
- `services/report/`:
  - `record.py`: the anonymised decision record, and the view the model sees;
  - `checker.py`: the fact checker (rules in `docs/REPORT_WRITER.md` §1);
  - `template.py`: the fallback and baseline;
  - `writer.py`: Qwen3-4B plain (LoRA scale 0) with the JSON schema, one retry with the checker's errors, then the
    template + `report:template_fallback`;
  - `schema.json`.
- `POST /report` (contracts `ReportRequirement`, `ReportIn`, `ReportOut`); `REPORT_*` settings in
  `config/.env.example`.
- **Prompts:** `prompts/report_writer/v0.md` (naive), `v1.md` (facts-only rules + example + retry), `v2.md` (+ the
  exact req_id list, the one-quote rule, missing must-haves in their own words; **chosen on dev**). Three rows in
  `prompts/PROMPT_LIBRARY.md` with the dev before/after numbers.
- **Evaluation:**
  - `scripts/make_report_records.py`: 28 dev + 28 test records from the production Matcher + Judge rows and the T08b
    gate, plus 2 flagged copies per split;
  - `scripts/eval_report_writer.py`: the measures, peak VRAM, and the summary;
  - results in `eval/results/2026-10-19_report_writer/`.
- **n8n:**
  - "Report Writer" node after `HTTP /outcome`, before Result and Switch;
  - Result has a `report` block;
  - the recruiter Wait form shows the summary, the requirement lines and the flags;
  - the outbox letters use the checked `candidate_letter` (a human-decided review gets a short fixed letter);
  - imported, published, re-exported and cleaned (`n8n/hiresignal_v1.json`, 33 nodes); `n8n/README.md` updated.
- **e2e:** one run per outcome type: P50 invite, P02 reject, P15 review (`eval/results/2026-10-19_n8n_e2e_report/`).
- `tests/test_report.py` (21):
  - the checker catches an invented quote, invented quoted text, a wrong decision, a wrong score, a name, a protected
    word, a placeholder, a dropped must-have, an invented requirement, internals in the letter, a reject letter
    without the human-review right, a wrong outcome word, and a dropped flag;
  - a review case has no letter;
  - the template passes the checker on all 56 records;
  - retry → template fallback; retry → fixed; invalid JSON / missing keys;
  - the `/report` contract;
  - the n8n node contract.
- `docs/REPORT_WRITER.md`.

## 2. Evidence (real-GPU)

| setup | split | pass, first try | pass after retry | template fallback | errors per report | must-haves covered | s / report | peak VRAM MiB |
|---|---|---|---|---|---|---|---|---|
| template | dev | 28/28 | – | – | 0 | 150/150 | 0.00 | 0 |
| 4B + v0 | dev | 0/28 | 0/28 | 28/28 | 2.29 | (template) | 13.0 | 3,267 |
| 4B + v1 | dev | 19/28 | 22/28 | 6/28 | 0.79 | 150/150 | 14.1 | 3,267 |
| **4B + v2** | dev | **27/28** | 27/28 | **1/28** | **0.11** | 150/150 | 10.8 | 3,267 |
| 0.6B + v2 | dev | 2/28 | 3/28 | 25/28 | 3.00 | (template) | 12.9 | 4,910 (two servers) |
| template | test | 28/28 | – | – | 0 | 151/151 | 0.00 | 0 |
| **4B + v2** | **test** | **24/28** | **25/28** | **3/28** | 0.32 | 151/151 | 11.7 | 3,267 |

- **Chosen: Qwen3-4B plain + v2.** It has the best dev pass rate, adds no extra VRAM (3,267 MiB = the llama-server
  already loaded), takes ~11 s per report, and the template catches the rest.
- **v0 lost** on every rule: no human-review right in 23 reject letters, edited quotes, dropped requirements, letters
  for review cases, internals told to the candidate.
- **0.6B lost:** 25/28 fallbacks; it needs a second server.
- **All test fallbacks** are quote edits: the model joins several quotes into one or shortens one.
- **0.6B time box:** started 01:16:17, finished 01:22:29 (about 6 min), on port 8091, stopped after the run.
- **Hand-read** 5 dev reports (invite P50, reject P51, review P48 → template fallback, photo-flag P01, swap-flag P03)
  plus the failure P42. Two good examples and one failure are pasted in `docs/REPORT_WRITER.md` §3 (anonymised: the
  record holds no identity).
- **n8n e2e** (prompt v2):

  | run | execution | outcome | report source | Report Writer node | letter |
  |---|---|---|---|---|---|
  | P50 | 37 | invite | LLM, first try | 9.8 s | outbox letter = the checked letter |
  | P02 | 38 | reject | LLM, first try | 9.8 s | outbox letter = the checked letter |
  | P15 | 39 | review | LLM, first try | 9.0 s | form shows the report |

  All three: identity found 0.
- **Tests:** `pytest -q` → `464 passed, 1 skipped` (the Chroma store test).

## 3. Not done / problems
- **The checker checks facts, not meaning.** It let through:
  - a line that contradicts its decision (P01: "Met: … no explicit 4 years … confirmed");
  - a reject letter that lists nice-to-haves as "required points" (P51).

  Both are listed in `docs/REPORT_WRITER.md` as limits.
- **The checker was changed on dev during the evaluation.** The "names each missing must-have" rule rejected correct
  letters ("a cloud provider" for "GCP or another cloud provider"); it now also accepts 2 content words. The dev runs
  were redone with the fixed checker; the first run is kept in `eval/results/2026-10-19_report_writer/old_checker/`.
- **The e2e first ran with v1.** The code default of `REPORT_PROMPT` was still v1 (`.env` does not set it). I found
  it after that first run, fixed the default to v2, and redid the three e2e runs. The first run is kept in
  `eval/results/2026-10-19_n8n_e2e_report_v1prompt/`.
- **The fixed rule is still a word check.** In that v1 run, P02 fell back to the template because the letter said
  "cloud" for "Experience with cloud (Amazon SageMaker)". That is safe, but less natural.
- **v2 was added beyond v0 → v1** (the library allows more versions); test was run once, with v2 only.
- **Small sets.** Only 1 invite (dev) and 0 invites on test; the flagged records are synthetic copies. The prompt
  example is a reject.
- **A human-decided review** gets a short fixed letter, not a generated one: the record of a review case has no final
  decision for the writer.

## 4. Questions for the Brain
1. Should a short "meaning" check be added? For example: a line's first word must match its decision, and a reject
   letter may only name MISSING **must-haves**. Both are simple code rules that would catch the two cases above.
2. Should a human-decided review case (form → reject) get a generated, checked letter (a second `/report` call with
   the human decision), instead of the fixed letter?

## 5. Suggested next step
Add the two small meaning checks (question 1) if approved; then final end-to-end runs and the demo.
