# Anonymiser fix (T06 Part 0) — before / after (rules only, CPU, no model)

Command: `.venv\Scripts\python scripts\eval_anonymiser.py --out eval\results\2026-10-18_anonymiser_fix\<before|after> --not-names eval\results\2026-10-18_anonymiser_fix\not_names.txt`
`before` = V2's `agents/profile/detect.py` (our copy before T06 was identical apart from the rule-6 header line; the
before run patches V2's `detect_rules` in, read-only). `after` = `services/profile/detect.py` with the fix:
1. no header-name search when the CV has no section heading (`has_headings` in `detect_rules`);
2. common tech / CV words added to `NOT_NAME`.

| set | measure | before | after |
|---|---|---|---|
| 10 synthetic CVs (V2 gold, `tests/fixtures/profile/`) | identity leaks | 0 / 65 | **0 / 65** |
| | other people readable | 0 / 5 | 0 / 5 |
| | CV facts kept | 65 / 67 | 65 / 67 |
| 40 real Djinni CVs (Reader + anonymiser) | CVs with a detected "name" | 18 | **1** |
| | `[NAME]` replacements | 45 | **1** |
| | detected values that are obviously not names (hand check) | 18 / 18 | 1 / 1 |

- `not_names.txt`: the 18 values detected before (checked by hand: tech terms, project titles, an award, a bank,
  "Seasoned Team Leader" ...; none is a person's name). Real detected values are stored only in
  `private/anonymiser_eval/<before|after>/names.json`.
- After: the one value left is a project title, "Cassava Leaf Disease" (a CV with headings; its words are not
  general tech words, so they were not added: that would be fitting the list to this CV).
- The 2 "facts lost" on the synthetic set are unchanged by this fix: gold `must_keep` expects "Ingénieure DevOps" and
  "Directeur technique", which T04's gendered-word fix now writes as "Ingénieur·e DevOps" / "Directeur·rice technique" (intended).
