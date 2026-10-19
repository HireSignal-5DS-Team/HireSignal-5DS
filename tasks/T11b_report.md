# T11b report — anonymiser took skill / project phrases as the candidate's name

**In plain words:** on CVs with a section heading, the anonymiser sometimes took a skill or project phrase ("Qlik
Sense") for the candidate's name and hid it everywhere. That no longer happens. Real names are still hidden, and every
counterfactual CV now gives exactly the same Matcher input as the original. On the 4 affected CVs no decision changed:
the hidden phrases were not decisive for those jobs.

## 1. Done
- **Found every case**: the anonymiser was run on all 52 gold CVs (the counterfactual bases are the same files).
  - 4 CVs had a false "name" (P06, P43, P45, P49), with 5 `[NAME]` replacements in total.
  - `eval/results/2026-10-19_name_overmask/before.csv` holds categories only: skill, ML technique, project title,
    platform title.
- **Cause.** On a Djinni CV with one section heading, all text before that heading counts as the "header". The header
  rule then took a 2–3 capitalised-word segment of a **bullet line or list item** as the name. Examples: "- BI tools:
  Cognos, …, Qlik Sense, …", "- Kaggle Notebooks Master".
- **Fix** (`services/profile/detect.py`, `find_name`): in the header search, a bullet line is skipped, and on a list
  line (`,` `;` `/`) only the first segment may be a name.
  - Designed on the one dev case (P45); no phrase list.
  - The T11 bare-name rule (a whole first line) is unchanged.
  - A suggested ESCO label/alt-label guard was checked and **not added**: none of the 4 phrases is an ESCO label, so it
    would add code without effect.
  - When no name is found, the existing `profile:name_not_found` flag applies; a skill is never masked "just in case".
- **Tests** (`tests/test_anonymiser_fix.py`):
  - one per phrase type (skill in a list, ML technique in a `/` list, project in a `;` list after a label, bullet
    achievement);
  - a real header name still masked, with the skill kept;
  - a name as the first segment of a list line still found;
  - "Fatma Trabelsi" still masked (`tests/test_bias.py`).
- **Approver answers to T11** (`docs/BIAS_REPORT.md`):
  - the Bias Auditor is described as two parts: a guard before the Matcher (the leakage check inside `/profile`) and
    the live swap after it (station 5, `/bias`). No new n8n node;
  - "no ablation for age, family, native language" is written as a limit;
  - the over-masking limit is replaced by the T11b result, and the remaining rule limit is described.
- `prompts/PROMPT_LIBRARY.md`: row `guard-anonymiser-name-t11b`.

## 2. Evidence
| measure | before (T11) | after (T11b) |
|---|---|---|
| gold CVs with a detected false "name" (52) | 4 | **0** |
| `[NAME]` replacements on gold CVs | 5 | **0** |
| synthetic anonymiser set: identity leaks / other people readable / facts kept | 0/65 / 0/5 / 65/67 | **0/65 / 0/5 / 65/67** |
| name-gender variants: Matcher input identical to the base | 288/312 | **312/312** |
| all families | 808/832 | **832/832** |
| injected names readable in the anonymised text | 0/312 | 0/312 |
| stored identity = the injected name | – | 312/312 |

**Chain re-run** (production settings, real-GPU), base CV of the 4 affected pairs, before vs after:

| pair | outcome before → after | gold | requirements agreeing with gold, before → after |
|---|---|---|---|
| P06 | reject → reject | reject | 4/8 → 4/8 |
| P43 | reject → reject | review | 6/8 → 6/8 |
| P45 | reject → reject | review | 4/6 → 4/6 |
| P49 | review → review | review | 7/8 → 7/8 |

No requirement decision changed. All 24 name-gender variants of these pairs now have an identical input and give the
same outcome.

**Tests:** `pytest -q` → `443 passed, 1 skipped` (the Chroma store test).

Results: `eval/results/2026-10-19_name_overmask/`:
- `before.csv`, `after/summary.json` (from `scripts/eval_anonymiser.py`);
- `bias/` (`scripts/eval_bias.py --pairs P06,P43,P45,P49 --families name-gender`), `decisions_before_after.json`,
  `NOTES.md`.

## 3. Not done / problems
- **The new rule can miss a real name written inside a bullet or list line**, for example "Skills: Python, Sara Ben
  Ali". This is unlikely in a CV header, and the synthetic set shows no new miss. Written as a limit in BIAS_REPORT §6.
- **No decision improved.** On P43 and P45 the gate still rejects where gold says review. The anonymiser is not the
  cause: with the skill back in the text, the decisions are the same. The cause itself was not analysed here.
- `scripts/eval_anonymiser.py` still calls its real set "real 40"; it now reads all 52 files in `data/processed/cvs/`.

## 4. Questions for the Brain
- None.

## 5. Suggested next step
Report Writer (station 7).
