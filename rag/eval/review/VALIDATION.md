# Validation of the approved review decisions (2026-10-14)

Provenance: decisions produced by an **AI-assisted review (Claude)** and **approved by the project owner**.
This is user-approved AI-assisted adjudication, **not independent human annotation**; no inter-annotator
agreement can be reported. Source file: `decisions_ai_assisted_2026-10-14.csv` (43 rows: 31 ACCEPT,
11 CORRECT, 1 REJECT). All 43 `qid`s match `eval/queries.jsonl` and the frozen `review_sheet.csv` exactly.

Every correction was checked against the indexed sources before being applied (`review.py apply` refuses the
whole file if one check fails). SHA256 of `eval/queries.jsonl` and `eval/results/results.csv` were
verified unchanged after applying.

## The 11 CORRECT decisions

| qid | Kind of correction | Check against source | Applied |
|---|---|---|---|
| E14 | Gold: 4th URI added (OR semantics) | `software design methodologies` (8ff015a0…) is in the 1,621 subset and its text mentions Scrum; the 3 original URIs are kept | yes |
| N01 | No-answer → ESCO query | `manage ICT virtualisation environments` (ae4f0cc6…) is in the subset; its text names "Docker, Kubernetes" | yes, type `none` → `esco` |
| N02 | No-answer → ESCO query, broad related skills | `business intelligence` (143769cb…) and `deliver visual presentation of data` (c3e36d05…) are in the subset; no Power BI concept exists | yes, type `none` → `esco` |
| J06 | Gold replaced | "one year of specialized experience equivalent to the GS-12 level in the Federal service" occurs verbatim once in usajobs-883691200 | yes |
| J17 | Gold completed | full sentence occurs verbatim once in usajobs-883511200 | yes |
| J19 | Gold shortened | "Python required" occurs verbatim once in usajobs-884225200 | yes |
| J01 | Question wording only | gold unchanged; new wording taken from the note | yes |
| J09 | Question wording only | gold unchanged | yes |
| J13 | Question wording only (FR) | gold unchanged | yes |
| J04 | Question wording + note that the gold is incomplete; **no corrected gold supplied** | see flag below | wording only; gold kept; **flagged** |
| J10 | Question wording + note that the gold is incomplete; **no corrected gold supplied** | see flag below | wording only; gold kept; **flagged** |

### Flag: J04 and J10 (gold not completed, by design)

The reviewer noted that both gold quotes are only the first item of a longer GS-14 specialized-experience list,
but left `corrected_gold` blank. No gold was invented. The original quotes are kept as **locators**: each
lies inside the complete passage, so a retrieved chunk covering the quote is at the right place. The complete
passages exist verbatim and contiguously in the sources and can be adopted as gold if the project owner
confirms:

- J04 (usajobs-883337000): from "GS-14: One year of specialized experience, equivalent to the GS-13 grade level
  in the Federal service, ..." through item 4 ("routinely explaining complex technical issues, ..."). Note: the
  list has **at least 4 items**, not 3 as the review note states.
- J10 (usajobs-886606600): from "GS-14: 1) Demonstrated experience advancing AI/ML and analytics initiatives ..."
  through item 6 ("... strengthen risk detection and decision-making.").

## The REJECT decision

J22 ("compétences informatiques exigées pour ce poste") is excluded from the reviewed set and from every
reviewed metric denominator. Its full record and the reason are kept in `rejected_queries.jsonl` and
`changelog.md`. The suggested rewording in the note was **not** applied (a rejected query is not rewritten).

## Resulting reviewed set

`eval/queries_reviewed.jsonl`: 42 queries = 16 ESCO (14 + N01, N02), 24 job, 2 no-answer (N03, N04).
