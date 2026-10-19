# T15 report — before/after iteration for the Job Agent and Profile Agent prompts

## In plain words
- **Job Agent (reads a job post, lists its requirements).** The new prompt v2:
  - lists one requirement per idea;
  - takes only the first way to qualify;
  - knows "a plus" / "required" cues;
  - treats attitudes like "willingness to do research" as nice-to-haves.

  Tested once on new job posts: it finds a little more (F1 0.700 → 0.712) and gets must vs nice right much more often
  (71% → 87%). It invented nothing.

  One new mistake: on one post it took the "Tasks" list (what the job does) as requirements. In production, the
  recruiter confirms the list before a run.
- **Profile Agent (reads the CV into skills / jobs / degrees).** v1's answers were cut off on 41% of the test CVs,
  losing skills. The fix writes each CV line once with all its skills, instead of once per skill.
  - Tested once: no CV is cut any more, the job's skill words found in the CV went from 28 to 59 of 70, and it is 3×
    faster.
  - A first try (v2) fixed the cutting but lost skills. v3 fixed that, with a small code guard.
- **Both are now in production** (job-v2, profile-v3), chosen on dev.
  - The final-evaluation decisions cannot change: the Matcher reads the CV text, not the profile, and the final
    evaluation used confirmed job cards.
  - One run without a card went through n8n with the new Job Agent and gave the right outcome.
- Also fixed: a crash in `/profile` when the model returned a skill name made only of punctuation.

## 1. Done
- **Prompts**
  - `prompts/job/v2.md` (new).
  - `prompts/profile/v2.md` (measured, not adopted) and `prompts/profile/v3.md` (production).
  - v1 files unchanged; the Matcher prompt untouched.
  - Version switch: `JOB_PROMPT_VERSION` / `PROFILE_PROMPT_VERSION` (defaults `job-v2` / `profile-v3`, in
    `config/.env.example`).
- **Code**
  - `services/job/prompts.py`, `services/profile/prompts.py`: version files and the env switch.
  - `services/profile/parse.py`:
    - `_expand_skill_groups`: grouped skills become the same `Skill` items, so the ParsedCV contract is unchanged;
    - `_reanchor`: a grouped name not written in its line gets the CV line that names it; never applied to v1-style
      items;
    - empty-name crash fix.
  - `services/job/scoring.py`: copied from V2 `agents/job/scoring.py`, with the header line.
- **Evaluation**
  - `scripts/eval_job_prompts.py`, `scripts/eval_profile_prompts.py`, `scripts/profile_example.py`.
  - `eval/job_agent/` (V2's 10 USAJOBS offers, public domain, with V2's gold cards; README).
  - `eval/profile_agent/` (V2's parse gold for the 10 synthetic CVs).
- **Results:**
  - `eval/results/2026-10-19_job_prompts/`;
  - `eval/results/2026-10-19_profile_prompts/`;
  - `eval/results/2026-10-19_n8n_e2e_job_v2/`.

  Each has a `config.json`; all are real-GPU (plain Qwen3-4B on llama-server).
- **Docs**
  - `prompts/PROMPT_LIBRARY.md`: overview rows; new rows job-v2, profile-v2, profile-v3; the "Not done" note replaced
    by the one open failure.
  - `docs/FINAL_EVAL.md`: §3, 2 rows; §4, the two limits updated.
- **Tests:** `tests/test_t15_prompts.py` (12); `tests/test_job_agent.py` and `tests/test_profile_parse.py` now follow
  the production version.

## 2. Evidence

### Part A — Job Agent v1 → v2
- **Set:**
  - V2's 10 USAJOBS offers with gold cards, plus our J1–J4 with the recruiter-confirmed cards.
  - Split fixed before any run, by sorted id: dev = 5 USAJOBS + J1, J2 (65 gold sentences); test = 5 USAJOBS + J3, J4
    (46).
- **Match rule:** V2's. Quotes match when one contains the other or difflib similarity ≥ 0.60; one-to-one, best pairs
  first.
- The few-shot examples come from 3 dev posts (883337000, 883386100, J2), so the dev numbers on those 3 are
  optimistic. That is why the 4 other dev posts are shown separately.

| measure | dev v1 | dev v2 | dev v1 → v2, 4 posts not used as examples | **test v1** | **test v2** |
|---|---|---|---|---|---|
| sentence precision / recall | 0.646 / 0.815 | 0.705 / 0.954 | 0.623 / 1.000 → 0.649 / 0.974 | 0.648 / 0.761 | 0.638 / 0.804 |
| **sentence F1** | 0.721 | **0.810** | 0.768 → 0.779 | 0.700 | **0.712** |
| must / nice accuracy (matched) | 0.868 | 0.919 | 0.842 → 0.865 | 0.714 | **0.865** |
| skills F1 / strict F1 | 0.760 / 0.615 | 0.792 / 0.622 | 0.849 / 0.690 → 0.879 / 0.615 | 0.826 / 0.504 | 0.800 / 0.578 |
| invented quotes (dropped) | 0 | 0 | – | 1 | 0 |
| verbatim share of raw proposals | 1.000 | 1.000 | – | 0.897 | 0.966 |
| soft attitudes kept as must | 1 | 0 | – | 0 | 0 |
| wrong splits / merges | 8 / 7 | 9 / 5 | 8 / 4 → 8 / 4 | 2 / 3 | 2 / 1 |
| latency per offer | 23.6 s | 22.2 s | 28.4 → 23.5 s | 19.2 s | 17.2 s |

**Decision, on dev before test:** adopt v2.
- The main measure (sentence F1) rose by +0.089, must/nice accuracy rose, soft attitudes kept as must went 1 → 0,
  there were no invented quotes, and latency stayed the same.
- Splits rose by 1: on 883386100, v2 finds the GS-11 requirement that v1 missed, and also takes it twice.
- On the 4 dev posts that are not examples, strict F1 dropped (0.690 → 0.615). This is reported, not hidden.

**Test (run once):**
- F1 +0.012; must/nice accuracy +0.151; strict F1 +0.074; merges 3 → 1; no invented quote.
- Skills F1 −0.026.
- **New failure:** J3's "Tasks:" list (duties) was taken as requirements, so J3's F1 fell from 0.94 to 0.70.

**Before/after example** (test offer usajobs-884301900, "Required Competencies: Attention to Detail - is thorough …
Customer Service - … Oral Communication - … Problem Solving - …"):
- v1 kept 2 of the 4 competencies ("Oral Communication - Expresses information …" and "Problem Solving - …",
  category other).
- v2 kept all 4 as `must` / `skill`.
- On dev, v1 missed all 10 competencies of 883337000 and v2 found them. That post is a few-shot source, so the dev
  number is optimistic.

**Soft trait:** J2 "Wiliness to do research on business logic" was must in v1 and is nice in v2 (gold: nice). J2 is
itself a few-shot source, so this only shows the rule is applied.

**e2e without a card** (`eval/results/2026-10-19_n8n_e2e_job_v2/`): P02 through the n8n webhook, `/job` with job-v2,
execution 75.
- Outcome reject = gold, in 84.8 s, identity found 0.
- The card had 20 requirements, because code splits one item per skill term (unchanged since T06).
- "Strong working knowledge of SQL, Teradata preferred" became nice (gold: must). The mixed must/nice sentence is not
  fixed.

### Part B — Profile Agent v1 → v2 → v3
- **Input:** as `/profile` does it (anonymiser + leakage check + injection removal).
- **Set:**
  - dev = 26 dev-pair CVs + K01, K02 + synthetic p01–p05;
  - test = 26 test-pair CVs + K03–K05 + synthetic p06–p10.
- 800-character chunks and 768 output tokens, unchanged.

| measure | dev v1 | dev v2 | dev v2 + guard | dev **v3** | **test v1** | **test v3** |
|---|---|---|---|---|---|---|
| CVs cut (`partial_extraction_requires_review`) | 7/33 | 0/33 | 0/33 | **0/33** | 14/34 | **0/34** |
| calls cut at 768 tokens | 18/86 | 0/77 | 0/77 | 0/77 | 40/116 | 0/96 |
| JSON valid (calls) | 0.791 | 1.000 | 1.000 | 1.000 | 0.655 | 1.000 |
| requirement terms in the CV found among the skills | 31/53 | **24/53** | 33/53 | **34/53** | 28/70 | **59/70** |
| raw skill names written in the CV | 0.949 | 0.941 | 0.941 | 0.947 | 0.965 | 0.958 |
| synthetic CVs: skills precision / recall (V2 gold) | 1.0 / 0.853 | 1.0 / 0.912 | 1.0 / 0.912 | 1.0 / 0.912 | 1.0 / 0.714 | 1.0 / 0.800 |
| experience / education items | 45 / 18 | 42 / 19 | 42 / 19 | 44 / 18 | 48 / 15 | 51 / 15 |
| latency per CV | 18.5 s | 7.7 s | 7.7 s | 7.5 s | 29.0 s | 9.6 s |

**v2 was not adopted.** It fixed the cutting but lost requirement terms (31 → 24), for two reasons:
- The model put skills from several lines under one line, and code then dropped every name not written in it. P31
  kept 0 of its 5 skills.
- The header "English level: upper" was no longer read as the skill English (5 CVs).

**v3** answers both: a prompt rule plus the code guard `_reanchor`. The guard alone gives 33/53 and v3 gives 34/53.

**Decision, on dev:** adopt v3.
- It fixes the target failure and finds more terms (31 → 34); synthetic recall rose and is 2.5× faster.
- Experience / education totals are flat (−1 / 0). Per CV, the counts move in both directions: P48 lost 4 experience
  items, p03 lost 2 (wrong evidence line), K01 gained 7, P19 / P25 / P45 gained 1 each. This is reported, not hidden.

**Test (run once):** all measures improved or stayed the same, except raw skill names written in the CV (0.965 →
0.958).

**Before/after example** (`eval/results/2026-10-19_profile_prompts/example_P44.json`, test pair P44, first chunk
"Programming languages: Python, Java, SQL / Relational databases: Oracle, MSSQL, …"):
- v1 wrote `{"name": "Bitbucket", "evidence": "Version control tools: Git, GitHub, Bitbucket"}, …` with each line
  repeated per skill. It was cut at 768 tokens (`finish_reason=length`), so the chunk gave 0 items.
- v3 answered in 290 tokens (`finish_reason=stop`): one group with all 25 tools.
- v3 still put several lines under one evidence here; the guard re-anchors each name to its own line.

### Part C — production and checks
- `job-v2` and `profile-v3` are the code defaults and are in `.env.example`.
- **Final-evaluation decisions unchanged, by construction:**
  - The Matcher reads the CV text, not the profile, and the final evaluation used confirmed cards.
  - The final evaluation's 13 profile-cut results (`profile:partial_extraction_requires_review`) only listed that flag:
    gate `pair_flags="info"`, and the flag is not in rule 0.
- **Crash found and fixed:** the first v3 test run crashed on a skill name of only punctuation (pydantic
  `string_too_short`). Before the fix this would have been a 500 from `/profile` with any version. Now the item is
  dropped with a note (test added), and the v3 test was re-run.
- **Tests:** `pytest -q` → **514 passed, 1 skipped**.

## 3. Not done / problems
- **Job v2 takes a Djinni "Tasks:" duties list as requirements** (test J3). The dev examples include experience
  activities as requirements (USAJOBS style), and v2 generalised that. A fix would need a v3 with a dev example of a
  duties list, then a new test set, because this test set is now used.
- **Mixed must/nice sentences** ("SQL, Teradata preferred") are still one kind for the whole sentence.
- **Small job set:** 7 offers per split. The dev numbers on the 3 few-shot posts are optimistic (shown separately).
- **Profile v3 experience counts** move per CV: some CVs lose items (P48, p03), others gain.
- **Time box:** this took longer than ~1.5 h because of the v2 → v3 profile step and the crash fix.

## 4. Questions for the Brain
1. The gate T08b note said that treating profile warnings as review reasons would remove the 4 false rejects, but
   send 46% to review. Most of those warnings were profile truncation, which v3 removes. Re-check that option on dev?
   It would mean a re-run of the gate on new profile flags; no model run is needed for the Matcher.
2. Should Job v3 (a duties-list example) be done, or is the confirmed-card step enough for the exam?

## 5. Suggested next step
Use the before/after tables and the two examples in the report and slides (prompt-engineering part).

## 6. Push
See the end of this report.
