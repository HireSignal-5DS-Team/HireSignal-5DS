# Profile Agent

Reader text → **two files**, kept apart on purpose:

| File | Goes to | Contains |
|---|---|---|
| `out/<cv_id>.cv.json` | n8n → Matcher | the team's CV `{cv_id, text, structured}`; `text` = the **anonymised** CV |
| `private/<cv_id>.identity.json` | **nowhere** (this machine only, git-ignored) | name, email, phone, links, address, personal details |

It replaces the team's `cv_from_reader` adapter, which sent the CV **with** the name to the Matcher.
`cv_id` is random (`cv-1a2b3c4d`): the file name often holds the person's name, so it is never used.

> Status: steps 1-3 (privacy) done and tested on the laptop. Step 4 (skills / education /
> experience with the shared plain Qwen) built and tested with fake models; first real run pending.

## How it works

```
Reader text ─► 1. find identity ─► 2. hide it ─► 3. leak check ─┬─► anonymised text ─► 4. read it (Qwen) ─► ParsedCV
                                                   ▲             │        + identity (local)
                                                   └─ leak: hide ┘   still a leak -> needs_human_review
```

**1. Find** (`detect.py`, rules, always on):
- contact: email, phone (years and date ranges are not phones), URL / LinkedIn / GitHub / `@handle`, address;
- the name: a `Name:` / `Nom :` + `Prénom :` label → else the CV header (lines before the first heading)
  → else words of the email address found in the CV (name only in the footer);
- bias proxies: date of birth, age, gender, Mr / Mme, nationality, marital status, place of birth, religion;
- other people with a title (`Dr. Leila Haddad`, `M. Sami Gharbi`): hidden, **not** stored.

Optional NER models (`ner.py`, CPU, no GPU needed) add what rules miss:
`oksomu/resume-ner` (English) and `urchade/gliner_multi_pii-v1` (multilingual, French too).

**2. Hide**: every form of the name (`John Smith`, `SMITH`, `J. Smith`, `Smith J.`, without accents,
`John_Smith`), every repeat of an email / phone (even written another way). Placeholders:
`[NAME] [EMAIL] [PHONE] [URL] [ADDRESS] [PERSONAL]`. Overlaps: the union is hidden (privacy first).

**3. Leak check**: searches the result again like an attacker would: identity values, the name glued in a
token (`johnsmith92`), fresh pattern matches. Found → hidden too. Still found → `needs_human_review`.
Also flagged: name not found, or an NER model asked for but not running.

The privacy report in `structured.privacy` holds **counts only**, never a personal value.
The Reader's warnings are redacted too; its `file_name` and `sections` are not passed on.

No photo handling: modern CVs have none (team decision).

**4. Read** (`parse.py`, prompt `profile-q1` in `prompts.py`): the team's plain Qwen reads the
**anonymised** text, one call per group of sections, into `ParsedCV` = skills, education
(degree, field, institution, end), experience (title, company, start, end), each with an exact quote.
Code then checks every quote and value against the CV, normalises dates (`2020-06`, `present`),
merges duplicates, and writes every repair in `uncertain`. Details: `prompts/PROMPT_LIBRARY.md`.
It lands in the Matcher CV as `structured.profile` (never used as evidence by the Matcher).

## Run it

With Ollama and the same Qwen as job-q1:

```
$env:HS_LLM_BASE_URL = "http://127.0.0.1:11434/v1"
$env:HS_LLM_MODEL = "hf.co/unsloth/Qwen3-4B-Instruct-2507-GGUF:Q4_K_M"
python scripts\run_profile_agent.py eval\profile_agent\cvs\p01_en_classic.txt
python scripts\eval_privacy.py
python scripts\eval_profile_parse.py
```

Privacy steps only, without Qwen: add `--no-parse`.

With the NER models (once, on the laptop: `pip install -r requirements-profile.txt`; the models download
from Hugging Face on the first run, ~1.5 GB in total, then run offline):

```
python scripts\eval_privacy.py --ner gliner resume-ner
```

## Results (10 synthetic CVs, EN + FR, invented people)

`eval/profile_agent`: each CV has a gold file listing what must disappear (65 identity pieces), other
people's data (5), and CV facts that must stay (67 companies, dates, skills). The checker is separate
from the agent's own leak check, so the agent does not grade itself.

| Detectors | Identity leaks | Other people readable | Facts kept | Time per CV (laptop CPU) |
|---|---|---|---|---|
| rules | **0 / 65** | 0 / 5 | 67 / 67 | < 0.01 s |
| rules + GLiNER + resume-ner | **0 / 65** | 0 / 5 | 67 / 67 | ~0.3 s (+16 s to load) |

On this set the models add nothing (the rules already catch everything), so they stay optional
(`--ner`). The first model run hid every "s" of a French CV (word pieces taken as places); the
guards added since are tested with that real output.

Limits: 10 CVs written by us (a second, unseen set is needed for the final report); gendered words in
running text ("Ingénieure", "she") are not hidden; a company sharing the candidate's surname is hidden too.

## Tests

```
python -m pytest -q tests/test_profile_privacy.py tests/test_profile_parse.py
```
