# Data card

Downloaded 2026-10-18. Raw files live in `data/raw/` (git-ignored). Counts below come from
`scripts/djinni_stats.py` (output: `data/stats/djinni_stats.json`) and `data/stats/kaggle_pdf_counts.txt`.
Synthetic data (bench-v1, `data/processed/bench-v1/`) is described in its own README. It is for development
and regression only and is not covered here.

## 1. Djinni Recruitment Dataset, English part (real, main source)

| field | value |
|---|---|
| links | https://huggingface.co/datasets/lang-uk/recruitment-dataset-candidate-profiles-english (revision `86255174`) and https://huggingface.co/datasets/lang-uk/recruitment-dataset-job-descriptions-english (revision `b56a6054`); project: https://github.com/Stereotypes-in-LLMs/recruitment-dataset |
| paper | Drushchak and Romanyshyn, "Introducing the Djinni Recruitment Dataset: A Corpus of Anonymized CVs and Job Postings", UNLP 2024 |
| licence | **MIT**: `license: mit` in both dataset cards (checked on 2026-10-18) |
| size | CVs: 210,250 rows, 11 columns. Jobs: 141,897 rows, 10 columns. Parquet: 237 MB + 146 MB |
| format | One parquet file per dataset. CV columns: `Position, Moreinfo, Looking For, Highlights, Primary Keyword, English Level, Experience Years, CV, CV_lang, id`. Job columns: `Position, Long Description, Company Name, Exp Years, Primary Keyword, English Level, Published, Long Description_lang, id` |
| content | Posts on the Djinni IT job platform (Ukraine), 2020-2023. The authors anonymised them. `CV` is the concatenation of Moreinfo, Looking For and Highlights |
| we use it for | the 40 real CV x job pairs for the human-labelled end-to-end evaluation (`data/labels/`); later possibly job postings for the RAG corpus |

**CV statistics:**
- Top Primary Keywords: JavaScript 33,980; QA 25,089; Design 15,068; Project Manager 12,499; Java 11,463; .NET 9,388; Marketing 8,984; **Python 7,588**; **Data Science 2,571**; Data Analyst 2,271; **Data Engineer 803**.
- CV length in characters: mean 944, median 751, 10th percentile 298, 90th percentile 1,892, maximum 7,372.
- Experience Years takes the values 0 to 11 in steps (0.5 up to 2.5, then whole years). 11 is the top bucket; we assume it means "10+", but this is not verified.

**Job statistics:**
- Description length in characters: median 1,629, 90th percentile 3,066.
- Top keywords: JavaScript 17,903; Java 8,712; DevOps 7,979; …; Python 5,735; Data Science 2,262.

**Personal data still in the CV text** (rough regex count, rows):
- email: 0;
- phone (≥ 10 digits, not a year range): 123;
- profile/messenger words (linkedin.com, github.com, t.me/, telegram, skype): 5,242;
- name phrases ("my name is", "name:"): 3,222. This one over-counts, for example "project name:".
- At least one hit: 8,499 of 210,250 (4.0 %).

Known limits:
- The CVs are short, self-written profile texts, not full CVs. There is no layout and no PDF, so this source does not test the Reader.
- Ukrainian market, 2020-2023. Some `Position` values are in Russian or Ukrainian.
- Anonymisation is not perfect (counts above). The labelling kit skips every CV with a hit.
- The MIT licence requires keeping its copyright notice with copies. Before we publish `data/processed/`, we need to add it (see the T03 report).

## 2. Kaggle Resume Dataset (real, PDF source)

| field | value |
|---|---|
| link | https://www.kaggle.com/datasets/snehaanbhawal/resume-dataset (downloaded with the Kaggle API) |
| licence | **CC0-1.0** (dataset metadata `licenses: CC0-1.0`; the Approver also confirmed it on Kaggle) |
| size | 2,484 PDFs in 24 category folders, plus `Resume.csv` with 2,484 rows (`ID, Resume_str, Resume_html, Category`). 119 MB unzipped |
| PDFs per category | ACCOUNTANT 118, ADVOCATE 118, AGRICULTURE 63, APPAREL 97, ARTS 103, AUTOMOBILE 36, AVIATION 117, BANKING 115, BPO 22, BUSINESS-DEVELOPMENT 120, CHEF 118, CONSTRUCTION 112, CONSULTANT 115, DESIGNER 107, DIGITAL-MEDIA 96, ENGINEERING 118, FINANCE 118, FITNESS 117, HEALTHCARE 115, HR 110, **INFORMATION-TECHNOLOGY 120**, PUBLIC-RELATIONS 111, SALES 116, TEACHER 102 |
| we use it for | Reader station (multimodality): real PDF layouts for the OCR path and the vision path. The text in `Resume_str` serves as the reference |

Known limits:
- The resumes were scraped from livecareer.com resume examples (dataset description). The uploader declared CC0, but the terms of the source site are not checked.
- The resumes are template examples, not real applications.
- Only 120 are IT resumes, and they are mostly IT support or management roles, not data or ML. Of the 120 `Resume_str` texts, 112 contain "support" or "help desk" and 101 contain "manager" or "director". Only 1 mentions "data scien", 0 mention "machine learning", and 7 mention "python".
- Some texts still start with a person's name (seen in at least 1 of the 120 IT texts). The Reader / Profile anonymiser must handle this.

## 3. Vanetik vacancy-resume matching dataset (real, small, ranking labels)

| field | value |
|---|---|
| link | https://github.com/NataliaVanetik/vacancy-resume-matching-dataset (commit `7ee8f043`; downloaded as a zip archive, no git) |
| licence | **GPL-3.0** (`LICENSE` file; GitHub API `spdx_id: GPL-3.0`) |
| paper | Vanetik and Kogan, "Job Vacancy Ranking with Sentence Embeddings, Keywords, and Named Entities", Information 14(8):468, 2023 |
| size | 5 vacancies (`5_vacancies.csv`: `id, job_description, job_title, uid`), 65 anonymised CVs (`.docx`), human annotations for CVs 1-30 by 2 annotators, annotation instructions (`.docx`). 2.2 MB |
| job domain | All 5 vacancies are **software developer** jobs: "Software Developer - .Net", "Remote Software Developer", "Junior Level Software Developer (1-4 years experience)", "Backend Software Developer" (LAMP, Drupal, ElasticSearch, Python, Go, AWS), and "Software Developer" (Java, C#, SQL). They are tech jobs, so the data was downloaded |
| we use it for | candidates: a second real check (ranking agreement with human annotators), and `.docx` input for the Reader |

Known limits:
- Very small.
- The labels rank the 5 vacancies **for each CV**. They are not requirement-level and do not rank CVs for a job.
- GPL-3.0 is copyleft. We keep the files only in `data/raw/` and do not copy them into the repo, so as not to redistribute them.

## 4. ESCO (RAG knowledge base)

`rag/data/esco/esco_ict_skills.jsonl`: 1,621 ICT skill concepts, copied from V2. The licence still needs to be checked in the RAG task (open from the T02b report).
