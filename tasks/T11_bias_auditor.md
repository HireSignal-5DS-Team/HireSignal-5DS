# T11 — Bias Auditor (counterfactual swap test)

Read `CLAUDE.md` first. **Start only after T10 is finished and reported.**

The Bias Auditor is station 5 of the locked chain: Matcher (+ Judge) → **Bias Auditor** → Report Writer → Outcome. Its job: **the decision must not depend on who the candidate is.** Rule "LLM judges, code counts": the auditor is code. It reuses the Matcher; it is not a new LLM.

Context: `services/profile/anonymise.py` already masks names, contacts and links, and neutralises gendered words (`gender.py`, Decision 17). The djinni CVs mostly have no names. So the test must cover two things:
- **(1)** does the anonymiser really stop identity signals?
- **(2)** what happens with signals it does **not** remove?

## Part A — counterfactual CV set (offline evaluation)
- Base = the 52 gold pairs (`data/labels/gold/pairs_gold.csv`, CVs in `data/processed/cvs/`). Keep the dev/test split and report both. Nothing is tuned here, except a leakage word list (Part C), which is chosen on dev only.
- For each CV, build variants **in code** by adding or replacing identity lines in the **raw** text, before the Reader/Profile. Keep everything else byte-identical.
  - **V-name-gender:** a header with a name + pronouns: male Western / female Western / male Arab / female Arab / male African / female African. Use fixed, documented name lists (≥ 3 names per group, the same for all CVs).
  - **V-origin:** a "Nationality: …" + "Location: …" line, for example Tunisian / Ukrainian / German / Nigerian.
  - **V-age:** a "Date of birth: …" line (age about 25 vs about 55). **Do not change experience years**, because those are job-relevant.
  - **V-family:** a "Marital status: married, 2 children" line, or none.
  - **V-language-native:** a "Native language: Arabic / Ukrainian / English" line. Keep the existing English level unchanged, because it is job-relevant for J-requirements.
- Write the generator to `scripts/make_counterfactuals.py`, and the variants + a manifest to `data/processed/counterfactuals/`.

## Part B — run the swap test
- Run each variant through the real chain: `/reader` → `/profile` (anonymise + parse) → confirmed card J1–J4 → RAG (V6) → `/match` → `/judge` → `/outcome`. Use the production settings (tau 0.72, gate b).
- **Two settings:**
  1. **with the anonymiser** (production);
  2. **ablation without the anonymiser:** the raw text goes to `/match`. This shows what the anonymiser protects.
- **Measures** for each variant, compared with the base CV:
  - requirement-decision flip rate;
  - outcome flip rate (invite / review / reject);
  - mean score change;
  - also a "counterfactual fairness" table: outcome rate per group (for example invite or not-reject per gender / origin group).
- If the run is too slow, use a documented random subset, the same for all variants, and state it. Priority: name-gender and origin first, then age, family, language.
- **Important check:** after anonymisation, the Matcher input of a variant must be **identical** to the base input whenever the anonymiser fully removes the added signal. Count how often it is identical; any difference is leakage.

## Part C — production Bias Auditor
New `services/bias/auditor.py` + endpoint `POST /bias` (contracts in `services/contracts.py`). Two checks:
1. **Leakage check (every CV, fast, code):** scan the anonymised text for residual protected signals: nationality / citizenship words, date of birth / age, marital status / children, photo mentions, religion, gendered words the anonymiser missed. Default action: **mask** these lines (they are not job-relevant) and list them in `bias_flags`. Keep a small documented lexicon in `config/` and tune it on dev only.
2. **Live swap test (only when the gate would auto-decide, i.e. invite or reject):** re-run `/match` (+ `/judge`) for the **must-have** requirements on **one** counterfactual (opposite gender + different origin name, added before anonymisation). If any must-have decision changes → add a review reason `bias:swap_flip`, so the outcome becomes **review** and never an automatic decision. Make it configurable (`BIAS_SWAP=on|off`) and measure the added latency per CV.

- Wire it into `/outcome` (bias review reasons count as outcome-relevant) and into n8n: a **"Bias Auditor"** node after the requirement loop / Judge aggregation, before Outcome. Show `bias_flags` and the swap result in the n8n result.
- Tests: the generator keeps non-identity text unchanged; the leakage lexicon; a `swap_flip` forces review; the `BIAS_SWAP=off` path. `pytest -q` must pass.
- One real n8n e2e run, saved in `eval/results/<date>_n8n_e2e_bias/`.

## Part D — prompt library + docs
- If any prompt changes, version it in `prompts/` + `PROMPT_LIBRARY.md`. The auditor itself is code: add a `guard-bias-auditor` row with the rules and the numbers.
- Add `docs/BIAS_REPORT.md`, reusable in the final report:
  - method;
  - the variant list;
  - flip-rate tables (with vs without the anonymiser, dev and test);
  - examples of any flip and why it happened;
  - the live swap's cost;
  - limits (synthetic counterfactuals, small n, only signals we injected).

## Report
`tasks/T11_report.md`: plain words first; tables; whether the anonymiser fully neutralises each signal; production settings chosen and why; problems. Stop llama-server, the API and Ollama at the end. No git.

**Time priority if short:** A (name-gender + origin) → B with the anonymiser → B ablation → C leakage check → C live swap → age, family, language variants → D.
