# T11 report — Bias Auditor (counterfactual swap test)

## In plain words
- **Test.** We added fake identity lines to all 52 real CVs: a name with pronouns from six groups (male and female ×
  Western, Arab, African), a nationality, a date of birth, a marital status and a native language. Then we checked
  whether the decision changes.
- **Production.** No decision and no outcome changed, over 832 variants.
- **Two real holes, now closed.**
  - The anonymiser let a **bare name** at the top of a CV ("Fatma Trabelsi") reach the Matcher, on every CV of our
    format.
  - "**Native language: Arabic**" was not hidden at all.
  - Both are fixed: the anonymiser now catches the name, and a new Bias Auditor check removes protected lines before
    the Matcher reads the CV.
- **Without anonymisation**, the same identity lines changed 37 requirement decisions, some only for certain names or
  countries, though no final outcome. This shows what the protection is for. This test was reduced to 13 CVs and the
  two main signals, for time.
- **Live check.** For every automatic invite or reject, the system re-checks the decision with a swapped identity. It
  usually costs well under a second, about 16 s when the Matcher has to re-run. A changed decision sends the case to a
  person.

## 1. Done
- **Part A:**
  - `scripts/make_counterfactuals.py` → `data/processed/counterfactuals/<pair>/<variant>.txt` + `manifest.json`;
  - 52 pairs × 16 variants: name-gender 6, origin 4, age 2, family 1, native language 3;
  - fixed name lists (3 per group); identity lines added before the raw text, the rest byte-identical (checked in code
    and in tests).
- **Part B:** `scripts/eval_bias.py`. Settings `prod` (anonymiser + leakage check) and `raw` (no anonymiser); the
  `--determinism` check; `--subset` / `--pairs`; `--report`. Results are in `eval/results/2026-10-18_bias/`.
- **Part C:**
  - **Anonymiser fix** (`services/profile/detect.py`): on a CV without section headings, the first non-empty line is
    taken as the name only if the whole line is a name.
  - `services/bias/auditor.py`:
    - `leakage_check` (protected label lines and placeholder-only lines removed, protected words masked; flags without
      text);
    - `counterfactual` (name replaced, or name + pronouns added; female Arab by default, male Western if the CV looks
      female);
    - `swap_decision`.
  - Lexicon `config/bias_lexicon.json` v1.
  - The leakage check runs in `/profile` (`run_profile_agent(..., audit=leakage_check)`), so the parse and the Matcher
    both see the audited text. `ProfileOut.bias_flags` and `bias:*` info flags were added.
  - `POST /bias` (contracts `BiasIn`/`BiasOut`): leakage flags, the gate's would-be outcome, and the live swap when it
    would be invite or reject and `BIAS_SWAP=on`. Identical Matcher input → no LLM call; otherwise must-haves re-run
    (`/match` + Judge). A change gives `bias:swap_flip`.
  - Gate: `bias:swap_flip` is in rule 0 (`ALWAYS_REVIEW`), so it always means review. A shared `_gate_settings()` is
    used by `/outcome` and `/bias`.
  - `config/.env.example`: `BIAS_SWAP=on`.
  - **n8n:**
    - new "Bias Auditor" node (Aggregate → Bias Auditor → Outcome input);
    - Outcome input adds the bias review and info flags;
    - Result has a `bias` block;
    - imported, published, re-exported and cleaned (`n8n/hiresignal_v1.json`, 32 nodes); `n8n/README.md` updated.
  - One real e2e (two pairs) in `eval/results/2026-10-18_n8n_e2e_bias/`.
- **Tests:** `tests/test_bias.py` (20). Covers the generator keeping non-identity text, base files equal to the
  sources, the lexicon (labels, placeholder lines, words, the dev false-positive check), the bare-name fix and the T06
  tech-word guard, the counterfactual, `swap_flip` → review, `BIAS_SWAP=off`, identical input → no LLM call, and the
  flip path. `tests/test_api.py` was updated (the contact placeholder line is now removed, with an info flag).
- **Part D:**
  - `guard-bias-auditor` row in `prompts/PROMPT_LIBRARY.md`; no prompt changed;
  - `docs/BIAS_REPORT.md`: method, variants, neutralisation, flip tables, flip examples, fairness, cost, limits.
- **T10 follow-up** (before T11): the scan files were swapped in the raw data, `MAPPING_FIX` was removed, the numbers
  were re-checked (identical), and the limitations were added to `docs/MULTIMODAL_REPORT.md` §7. Details are in
  `tasks/T10_report.md`.

## 2. Evidence (real-GPU)
**Does the anonymiser neutralise each signal?** Matcher input identical to the base, 52 pairs:

| family | T10 anonymiser | production (T11 name fix + leakage check) |
|---|---|---|
| name-gender | 0/312 (the full name reached the Matcher) | **288/312** |
| origin | 0/208 (`Nationality: [PERSONAL]`, location form differs by country) | **208/208** |
| age | 0/104 (`Date of birth: [PERSONAL]`) | **104/104** |
| family | 0/52 (`Marital status: [PERSONAL]`) | **52/52** |
| native language | 0/156 (`Native language: Arabic`, not masked) | **156/156** |

The 24 non-identical name variants come from 4 CVs (P06, P43, P45, P49) whose **base** anonymisation over-masks a tech
phrase as the "name". With a real name added, that phrase comes back. All 24 were run through the chain, and none
changed a decision.

**Determinism.** Re-running the base of 5 pairs gives equal decisions, quotes and outcome, 5/5.

**Swap test, production** (all 52 pairs, all 16 variants):

| split | variants | Matcher input identical | requirement flips | outcome flips |
|---|---|---|---|---|
| dev | 416 | 410 | 0 | 0 |
| test | 416 | 398 | 0 | 0 |

The mean score change is 0.00 for every family.

**Ablation, no anonymiser — reduced, see §3** (13 pairs, name-gender + origin):

| split | family | variants | requirement flip rate | outcome flips | mean score change |
|---|---|---|---|---|---|
| dev | name-gender | 42 | 0.054 | 0 | +2.79 |
| dev | origin | 28 | 0.114 | 0 | +5.96 |
| test | name-gender | 36 | 0.000 | 0 | 0.00 |
| test | origin | 24 | 0.006 | 0 | +0.29 |

- 37 must-have flips in 35 variants, all towards a more favourable label.
- Flips on 6 pairs:
  - 2 flip for every variant (a generic header effect);
  - 4 depend on the group: P11 (male Western and male African names + origins), P13 (male Arab name + origins), P29
    (Tunisian, Ukrainian, Nigerian), P02 (Ukrainian).
- Counterfactual fairness: outcome rates are equal for every group in both settings.

**Live swap cost:**
- identical input: 0.24 s (P06) and 0.07 s (P02), as "Bias Auditor" node time in n8n;
- input differs: 15.7 s for 5 must-haves (P45 on the live API, `swap_rerun_latency.json`).

**n8n e2e:**
- executions 32 (P06) and 33 (P02), both reject (would-be outcome reject);
- swap ran, identical input, no review reason;
- 1 placeholder-only line removed each;
- identity found 0/7 and 0/1; raw CV text in execution: no.

**Tests:** `pytest -q` → `432 passed, 1 skipped` (the Chroma store test).

## 3. Not done / problems
- **The ablation was reduced, for time.**
  - The full ablation (52 pairs × 16 variants at ~21 s per chain) would have taken about 5 h. A first 26-pair plan
    (~2.6 h) was stopped on the Approver's request.
  - Done instead: **name-gender + origin on a fixed subset of 13 pairs** (first 7 dev + first 6 test of the seed-11
    list, reusing every run already done).
  - So age, family and native language were measured **only in production**, with no no-anonymiser comparison, and
    the ablation numbers rest on 130 variants.
- **Production setting = anonymiser + leakage check.** The pre-T11 anonymiser alone was not run through the chain:
  all its variants differ from the base, so that would have cost as much as the ablation. Its leaks are shown in the
  neutralisation table.
- **Where check 1 runs.** The Locked chain puts the Bias Auditor after the Matcher (station 5). Its leakage masking
  can only protect the Matcher if it runs before it, so it runs inside `/profile`; `/bias` reports the flags again
  and runs the live swap at station 5.
- **Pre-existing anonymiser over-masking** on CVs with a section heading ("Qlik Sense", "Kaggle Notebooks",
  "Recommendation System", "Cassava Leaf Disease" taken as the name). It removes real skills from the Matcher's input,
  and in production it gives the live swap a wrong "name" to replace (seen in the P06 e2e). Not fixed here.
- **The live swap tests one counterfactual and the must-haves only.** It relies on determinism (checked on 5 pairs).
- **The counterfactuals are synthetic:** one fixed header format, and only the signals we injected.
- The Profile parse (LLM) was not run in the swap test; it does not feed the Matcher, and its flags are info only.

## 4. Questions for the Brain
1. Is it acceptable that the leakage check runs inside `/profile` (before the Matcher), while station 5 (`/bias`) only
   reports it and runs the live swap? The alternative is a separate n8n node between Profile and the loop.
2. Should the header-name over-masking ("Qlik Sense" taken as a name) get its own small task? It removes skills from
   the Matcher input on CVs with section headings.
3. Should the ablation for age, family and native language be run later (about 1 h on 13 pairs), or is production
   evidence enough for those?

## 5. Suggested next step
Report Writer (station 7). It can show `bias_flags` and the swap result in plain words in the candidate report.
