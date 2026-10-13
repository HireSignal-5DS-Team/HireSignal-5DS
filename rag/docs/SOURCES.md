# Knowledge-base sources and provenance

| Collection | Source | Version / date | Size | Format | Rights | Role in HireSignal |
|---|---|---|---|---|---|---|
| ESCO skills (ICT/data subset) | ESCO classification, European Commission, via the Tabiya CSV mirror `tabiya-tech/taxonomy-model-application`, commit `eb3e5f4`, folder `data-sets/csv/esco-v1.1.2` | Mirror folder says v1.1.2; its `model_info.csv` says "ESCO v1.1.1 (en)". We report it as **ESCO v1.1.x (en)** | 1,621 of 13,896 skills (see below) | JSONL, one concept per line | CC BY 4.0 (LICENSE file in the mirror folder). Attribution: "ESCO, European Commission" | Terminology only: synonyms and definitions of skills. It never adds requirements to a job. |
| Job postings | **Pending**: to be supplied by the team (see `data/jobs/README.md`) | — | target 15–20 postings | Markdown with provenance header | Checked per posting before commit | Source of employer-specific requirements |

## Why a mirror and not the official ESCO portal

`esco.ec.europa.eu`, `ec.europa.eu` and `data.europa.eu` are blocked (HTTP 403) by our cloud build
environment's network policy. The Tabiya mirror is a public GitHub repository that redistributes ESCO under
CC BY 4.0 with the original concept URIs. `build_esco.py` pins the commit and checks SHA256 hashes of the three
CSV files it uses, so the subset is reproducible. Limitation: v1.1.x, not the current v1.2.1. The concept URIs are
stable across versions, so this only affects concepts added in v1.2 (35 occupations, 42 skills, 196 knowledge
concepts according to the v1.2 release notes).

## How the ESCO subset is defined

Skills linked (essential or optional) to occupations in ISCO groups 25 (ICT professionals, incl. data scientist
2511.4 and data analyst 2511.3), 35 (ICT technicians), 212 (mathematicians, statisticians) and 1330 (ICT managers,
incl. chief data officer) = 110 occupations, plus all 440 transversal skills (teamwork, communication...), which
appear in most job ads but are linked to few occupations. Result: 1,621 concepts.

We planned to use ESCO's "digital skills collection" instead; the mirror does not contain collection files, so
the subset is derived from occupation links. Coverage was measured, not assumed: see `esco_coverage.md`.
29 of 38 frequent data/tech job-ad terms are found in the subset (30 in full ESCO). Tool names such as PyTorch,
scikit-learn, pandas, Docker, Kubernetes, AWS, Power BI and Tableau are **absent from ESCO itself**, so for those
the correct RAG behaviour is "no match", not a guess.
