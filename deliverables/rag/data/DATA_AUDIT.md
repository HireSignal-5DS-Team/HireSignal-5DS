# RAG data audit

Date: 2026-10-14. Scope: the two collections indexed by the HireSignal RAG. Nothing was regenerated, replaced or
synthesised; the originals were read only and are unchanged.

## Where the original files are

The RAG lives on branch `claude/gracious-fermi-ncuem4` (head `9232614`), not on `main`. The data files were
last changed in commit `139fcc7` (2026-10-13).

| Collection | Original file(s) in the repo | Format | SHA256 |
|---|---|---|---|
| ESCO skills | `rag/data/esco/esco_ict_skills.jsonl` | JSONL, 1,621 lines, 7 fields | `8c6a4b3d0f26b3fa524579ebfdffb45648ca754fa08ef43c6ac14926a93f4b29` |
| Job postings | `rag/data/jobs/usajobs-<control number>.md` (20 files) | Markdown, provenance header + text | per file, in column `rag_file_sha256` |

No CSV of either collection existed in the project. The CSVs here are exports, made by `export_csv.py`.

## Upstream sources (re-downloaded and hash-checked)

Both build scripts pin their upstream source by commit and SHA256. The exact files were re-downloaded and all
four hashes match the pins.

| File | Source | Pinned revision | SHA256 (matches pin) |
|---|---|---|---|
| `skills.csv` | github.com/tabiya-tech/taxonomy-model-application, `data-sets/csv/esco-v1.1.2/` | `eb3e5f445f6c0271641851dd2d27621d812c4662` | `9717a452…3fee2` |
| `occupations.csv` | same | same | `99ebee8b…7dcf0` |
| `occupation_to_skill_relations.csv` | same | same | `28e45655…eb6d5` |
| `2026_09.parquet` | huggingface.co/datasets/abigailhaddad/usajobs-scraping, `data/` | `9f202342df2d8db692c0ad973905a808b835db89` | `fb6e2e30…49c6a97` |

## Verification results

| Check | ESCO | Jobs |
|---|---|---|
| Rows | 1,621 | 20 |
| Unique IDs | 1,621 `doc_id` | 20 `job_id` |
| Duplicate rows / duplicate IDs | 0 / 0 | 0 / 0 |
| Repo data reproduced from upstream | Yes. All 1,621 `text`, `title`, `skill_type`, `reuse_level` values rebuild exactly from the upstream row. The `build_esco.py` selection rule yields exactly the same 1,621 URIs. | Yes. All 20 posting bodies rebuild byte-for-byte from the upstream rows. Title, organisation and open date match. |
| CSV round trip | Re-read CSV equals the JSONL, same row order | `rag_text` equals each `.md` body |
| Source URLs | 1,621/1,621 match `http://data.europa.eu/esco/skill/<uuid>` and equal the upstream `ORIGINURI` | 20/20 equal `https://www.usajobs.gov/job/<usajobsControlNumber>` |
| URLs opened live | **Not done**: `usajobs.gov` and `data.europa.eu` are blocked by the build environment's network policy | same |

## `esco_ict_skills_1621.csv`

1,621 rows, 26 columns, UTF-8 with BOM. Rows are in the JSONL order (sorted by URI).

| Columns | Origin | Missing values |
|---|---|---|
| `doc_id`, `source_type`, `title`, `skill_type`, `reuse_level`, `url`, `text` | JSONL fields, verbatim. This is what the RAG indexes. `text` = label + "Also known as" + description | `skill_type`: 1 (see below). Others: 0 |
| `ORIGINURI`, `ID`, `UUIDHISTORY`, `SKILLTYPE`, `REUSELEVEL`, `PREFERREDLABEL`, `ALTLABELS`, `DESCRIPTION`, `DEFINITION`, `SCOPENOTE`, `ISLOCALIZED` | Upstream `skills.csv` row, verbatim, joined on `doc_id = ORIGINURI` | `SKILLTYPE`: 1. `DEFINITION`: 1,621 (empty in ESCO for every row). `SCOPENOTE`: 1,592. Others: 0 |
| `source_dataset`, `source_mirror`, `source_commit`, `source_file`, `source_sha256`, `rag_file`, `rag_file_sha256`, `license` | Provenance, constant per row | 0 |

`ALTLABELS` holds several labels separated by line breaks, as in the upstream file.

Missing `skill_type`: `http://data.europa.eu/esco/skill/c13fb093-5ffb-491a-b8b7-fa2d42a57e2e`
("implement cloud security and compliance"). It is also empty in the upstream ESCO file, so this is a source gap,
not an export error.

Distributions: `skill_type` skill/competence 1,106, knowledge 514, empty 1. `reuse_level` sector-specific 665,
cross-sector 452, transversal 440, occupation-specific 64.

Licence: CC BY 4.0, attribution "ESCO, European Commission". Version: ESCO v1.1.x (en); the mirror folder says
v1.1.2, its `model_info.csv` says v1.1.1.

## `real_job_offers_20.csv`

20 rows, 64 columns, UTF-8 with BOM. Rows sorted by `job_id`.

| Columns | Origin | Missing values |
|---|---|---|
| `job_id`, `title`, `organisation`, `source_url`, `retrieved`, `rights`, `open_date` | `.md` provenance header, verbatim | 0 |
| `rag_file`, `rag_file_sha256` | Path and hash of the `.md` file | 0 |
| `rag_text` | `.md` body, verbatim: the exact text the RAG chunks and indexes | 0 |
| `rag_text_words` | Word count of `rag_text` (756–3,057, total 36,048) | 0 |
| `src_*` (53 columns) | The posting's full upstream row from `2026_09.parquet` (all original columns, prefixed `src_`) | `src_whoMayApply` 20, `src_positionExpireDate` 19, `src_hiringSubelementName` 8, `src_totalOpenings` 1, `src_education` 1. Others: 0 |

The full original announcement text is in `src_text` (the scraped page). The per-section originals are in
`src_jobSummary`, `src_majorDuties`, `src_qualificationSummary`, `src_benefits`, `src_howToApply` and the other `src_*` columns.
JSON-valued columns (`src_positionLocations`, `src_hiringPaths`, `src_jobCategories`) are kept as the upstream JSON strings.
Original spelling is kept, e.g. `usajobs-883691200` is titled "Al Software Engineer" (lowercase L) in the source.

### Differences from the raw upstream text (deliberate, documented)

1. **Contacts redacted.** E-mail addresses and phone numbers are replaced with `[contact removed]`, using the regexes
   and the rule in `rag/build_jobs.py` and `rag/data/jobs/README.md`. In `rag_text` this is the RAG's own data
   (2 replacements in 1 posting). In the `src_*` columns, 162 strings were redacted: `src_text` 116,
   `src_howToApply` 41, and 1 each in `src_requirements`, `src_qualificationSummary`, `src_additionalInformation`,
   `src_benefits`, `src_howYouWillBeEvaluated`. Unredacted values remain in the hash-pinned upstream parquet.
2. **Sections left out of `rag_text`.** The RAG keeps Summary, Duties, Conditions of employment, Qualifications,
   Education and Additional information. Benefits, How you will be evaluated, Required documents and How to apply
   are not indexed. They are still in the `src_*` columns.
3. **Line breaks.** The upstream scraper collapsed line breaks inside sections, so bullets are lost in the source
   itself.

Licence: announcements are US federal works, public domain (17 U.S.C. 105); the dataset is CC0 1.0.

## Opening in Excel

- Both files are UTF-8 with BOM, so accents and symbols display correctly.
- Excel limits a cell to 32,767 characters. Two columns of `real_job_offers_20.csv` exceed it and **will be
  truncated in Excel** (the CSV itself is complete): `src_text` (max 93,486 chars) and `src_positionLocations`
  (max 43,485 chars). `rag_text` (max 20,616) fits. To read a long cell completely, use the matching `.md` file or
  Python/pandas.
- Several text cells contain line breaks; Excel shows them inside the cell.

## Reproduce

```bash
git archive origin/claude/gracious-fermi-ncuem4 rag | tar -x -C /some/dir    # read-only copy of the RAG data
# download the 4 pinned upstream files into UP_DIR (see build_esco.py, build_jobs.py)
python deliverables/rag/data/export_csv.py /some/dir/rag UP_DIR
```

The script stops on any hash mismatch or any row that does not match upstream.

Output hashes: `esco_ict_skills_1621.csv` `3efb616e674ea579fe6f1afed2a34e41883ed1a0df7b82d17d51ccb55a603d48`,
`real_job_offers_20.csv` `ae2e5359ce45a47f9a2d3d12d5472b15ad8fe37d9b96bbc95207c190ab1a25b7`.
