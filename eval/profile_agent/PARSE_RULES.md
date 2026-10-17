# Gold rules for step 4 (reading the CV)

`parse_gold/<cv>.json` lists what a perfect reader should extract from each CV in `cvs/`.

- **skills**: every technology, tool, programming language, framework, method, certification and
  spoken language *named* in the CV (summary, experience, projects, skills, certifications, languages).
  One entry per skill; `["CEH", "CEH v11"]` = any of these spellings is right.
- **skills_optional**: reasonable extras ("ML pipelines", "Incident response"): not required,
  not counted as wrong.
- **education**: one entry per degree or diploma; `end` = year written.
- **experience**: one entry per job or internship, not projects; dates normalised
  (`2020-06`, `present`). "2021 2022 2023" counts as start 2021, end 2023.
- Facts hidden by the privacy step are not expected (p04: "ISG Sousse" becomes "ISG [PERSONAL]",
  because Sousse is also the candidate's birthplace, so the gold institution is "ISG").

Scoring (`scripts/eval_profile_parse.py`):
- skills: F1 on names (case, accents and spaces ignored);
- experience: matched on company (else title), F1 + accuracy of title / start / end on matched items;
- education: matched on institution (else degree), F1 + accuracy of degree / field / end.
