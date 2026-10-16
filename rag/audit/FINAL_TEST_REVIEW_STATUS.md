# Final test set — review status (audit 2026-10-15)

- Sealed file: `experiments/exp03_optimization/final_test_queries.jsonl`, 36 queries (12 job, 6 job no-answer,
  12 ESCO, 6 ESCO no-answer; 6 French), SHA256 `0a14b0cd…` — unchanged, **not evaluated**.
- Review sheet in the repository (`final_test_review_sheet.csv`, identical on branch `claude/vigilant-albattani-dmn3pk`):
  **36 rows, all decisions blank**. `check_final_review.py` → "NOT READY: 0 format problems, 36 unresolved rows".
- The AI-assisted review mentioned in the instructions (24 provisionally accepted, 12 flagged) is **not present** in the
  repository, on any branch, or in the session uploads. It has not been seen or validated.
- Whatever review is applied must be recorded as AI-assisted with the owner's approval unless a person independently
  checks each row against the source.

## How to complete it

1. For each row, open the evidence column (gold quote in context / ESCO entry) and the USAJOBS URL if needed.
2. Fill `decision (ACCEPT/CORRECT/REJECT)`, `reviewer` and `notes`; for CORRECT put the new gold in `corrected_gold`
   (job: verbatim quote, several separated by `||`; ESCO: exact ESCO label; no-answer: `no_match`).
3. Run `python rag/experiments/exp03_optimization/check_final_review.py` until it prints `VALID AND COMPLETE`.
4. Commit the sheet and explicitly approve the sealed evaluation. Only the frozen production configuration
   (structure + e5-small) and the two pre-registered in-budget candidates are then evaluated, once.

## Per-row verification checklist

| qid | type | lang | query | what to verify |
|---|---|---|---|---|
| TJ01 | job | en | perform data analysis with statistical software and share findings | the gold quote fully answers the question and is the best passage in that posting |
| TJ02 | job | en | statistcal softwar for data requests | the gold quote fully answers the question and is the best passage in that posting; **adversarial typos: is the query still answerable?** |
| TJ03 | job | en | review and optimise code for ML models and database queries | the gold quote fully answers the question and is the best passage in that posting |
| TJ04 | job | fr | traitement automatisé de données statistiques | the gold quote fully answers the question and is the best passage in that posting |
| TJ05 | job | en | role-based access control and data protection duties | the gold quote fully answers the question and is the best passage in that posting |
| TJ06 | job | en | SQL Server performance tuning and schema design | the gold quote fully answers the question and is the best passage in that posting |
| TJ07 | job | en | graph database work to uncover hidden networks | the gold quote fully answers the question and is the best passage in that posting |
| TJ08 | job | fr | surveiller les solutions d'IA en respectant la sécurité et l'intégrité des données | the gold quote fully answers the question and is the best passage in that posting |
| TJ09 | job | en | apply emerging AI technologies to improve automation | the gold quote fully answers the question and is the best passage in that posting |
| TJ10 | job | en | data ingestion, validation and preprocessing pipelines | the gold quote fully answers the question and is the best passage in that posting |
| TJ11 | job | fr | combinaison de mathématiques, statistiques et informatique dans le diplôme | the gold quote fully answers the question and is the best passage in that posting |
| TJ12 | job | en | what grade level must prior specialized experience equal | the gold quote fully answers the question and is the best passage in that posting; **paraphrase: does 'grade level' match the gold?** |
| TN01 | none | en | Is a PhD required for this role? | the requirement is really absent (job posting) / no ESCO concept fits (off-domain); **PhD absence checked by regex only** |
| TN02 | none | en | Kubernetes experience required? | the requirement is really absent (job posting) / no ESCO concept fits (off-domain) |
| TN03 | none | en | Does the job require French language skills? | the requirement is really absent (job posting) / no ESCO concept fits (off-domain); **French language absence** |
| TN04 | none | en | Salesforce platform administration | the requirement is really absent (job posting) / no ESCO concept fits (off-domain) |
| TN05 | none | en | experience with SAP ERP systems | the requirement is really absent (job posting) / no ESCO concept fits (off-domain) |
| TN06 | none | en | Is a commercial driver's licence needed? | the requirement is really absent (job posting) / no ESCO concept fits (off-domain) |
| TE01 | esco | en | R statistical programming | the listed ESCO concept(s) are correct and no other concept is equally correct; **ambiguous one-letter skill 'R'** |
| TE02 | esco | en | Java backend development | the listed ESCO concept(s) are correct and no other concept is equally correct; **Java vs JavaScript trap** |
| TE03 | esco | fr | programmation Java | the listed ESCO concept(s) are correct and no other concept is equally correct |
| TE04 | esco | en | dataa warehose design | the listed ESCO concept(s) are correct and no other concept is equally correct; **typos ('dataa warehose')** |
| TE05 | esco | en | data protection regulations | the listed ESCO concept(s) are correct and no other concept is equally correct |
| TE06 | esco | fr | gestion de projet | the listed ESCO concept(s) are correct and no other concept is equally correct; **two acceptable URIs (OR)** |
| TE07 | esco | en | web analytics tools | the listed ESCO concept(s) are correct and no other concept is equally correct |
| TE08 | esco | en | SPARQL queries on linked data | the listed ESCO concept(s) are correct and no other concept is equally correct |
| TE09 | esco | en | manage a relational database | the listed ESCO concept(s) are correct and no other concept is equally correct |
| TE10 | esco | fr | mathématiques | the listed ESCO concept(s) are correct and no other concept is equally correct |
| TE11 | esco | en | LDAP directory services | the listed ESCO concept(s) are correct and no other concept is equally correct |
| TE12 | esco | en | cloud monitoring and reporting | the listed ESCO concept(s) are correct and no other concept is equally correct |
| TX01 | none | en | embalming | the requirement is really absent (job posting) / no ESCO concept fits (off-domain) |
| TX02 | none | en | horse riding instruction | the requirement is really absent (job posting) / no ESCO concept fits (off-domain) |
| TX03 | none | en | glassblowing | the requirement is really absent (job posting) / no ESCO concept fits (off-domain) |
| TX04 | none | en | opera singing | the requirement is really absent (job posting) / no ESCO concept fits (off-domain) |
| TX05 | none | en | chimney sweeping | the requirement is really absent (job posting) / no ESCO concept fits (off-domain) |
| TX06 | none | en | sushi preparation | the requirement is really absent (job posting) / no ESCO concept fits (off-domain) |
