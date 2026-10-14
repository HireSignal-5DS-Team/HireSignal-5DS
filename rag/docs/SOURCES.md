# Knowledge-base sources and provenance

| Collection | Source | Version / date | Size | Format | Rights | Role in HireSignal |
|---|---|---|---|---|---|---|
| ESCO skills (ICT/data subset) | ESCO classification, European Commission, via the Tabiya CSV mirror `tabiya-tech/taxonomy-model-application`, commit `eb3e5f4`, folder `data-sets/csv/esco-v1.1.2` | Mirror folder says v1.1.2; its `model_info.csv` says "ESCO v1.1.1 (en)". We report it as **ESCO v1.1.x (en)** | 1,621 of 13,896 skills (see below) | JSONL, one concept per line | CC BY 4.0 (LICENSE file in the mirror folder). Attribution: "ESCO, European Commission" | Terminology only: synonyms and definitions of skills. It never adds requirements to a job. |
| Job postings | 20 real USAJOBS announcements (Sept 2026) from the Hugging Face dataset `abigailhaddad/usajobs-scraping`, revision `9f20234`, file `data/2026_09.parquet` (SHA256 pinned in `build_jobs.py`) | opened Aug–Sept 2026, retrieved 2026-10-13 | 20 postings, 756–3,057 words each (36,000 words total) | Markdown with provenance header, one file per posting | Announcements: public domain (US federal works, 17 U.S.C. 105). Dataset: CC0 1.0 | Source of employer-specific requirements |

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

## How the job postings were selected and assembled

- Candidates: September 2026 announcements in occupational series 1560 (data science), 1550 (computer science),
  1529 (mathematical statistics) and 2210 (IT management) whose title mentions data science, AI, ML, software
  engineering or statistics: 59 after removing duplicate duty texts.
- Selection: 20 postings, one per agency, chosen from titles only for role diversity (data scientists, AI/ML
  engineers, AI software engineers, statisticians, IT specialists in AI or data science), before any query was
  written. The list of control numbers is fixed in `build_jobs.py`.
- Assembly: the page's own sections, in page order, under the page's own headings (Summary, Duties, Conditions of
  employment, Qualifications, Education, Additional information). Section text is verbatim from the dataset.
  Benefits, How you will be evaluated, Required documents and How to apply are left out (application logistics).
  E-mail addresses and phone numbers are replaced with `[contact removed]` (2 replacements in 1 posting).
- Known data quirks, kept as is: the scraper collapsed line breaks inside sections, so bullets are lost; some
  passages appear in two sections (e.g. clearance text in Qualifications and Additional information).
- Why USAJOBS: it was the only source reachable from the build environment with unambiguous reuse rights. Other
  Hugging Face job-ad datasets (LinkedIn or job-board scrapes) carry a dataset license but no clear right to the
  ad text itself. Limitation: US federal postings are longer and more administrative than private-sector or
  Tunisian job ads.
