# Known-answer query set

`queries.jsonl`, one query per line. Write queries **before** looking at retrieval output.

| type | fields | scored as |
|---|---|---|
| `job` | `job_id`, `gold_quotes` (verbatim text from the posting, must occur exactly once) | scoped: filter to the posting, Hit@1; global: all postings, Hit@5 and MRR |
| `esco` | `gold_labels`, `gold_uris` (any listed URI counts) | Hit@1, Hit@5, MRR |
| `none` | `collection` (`job` or `esco`) | correct when the system returns `no_match` |

A job chunk is a hit when it comes from the gold posting and covers at least 50% of a gold quote's characters,
so fixed-size and structure-aware chunking are scored against the same evidence.

Labelling status: `labelled_by` is `human` or `ai-draft`; `verified_by` names the teammate who checked it.
The current 14 ESCO and 4 no-answer queries are **ai-draft** (gold URIs resolved by exact ESCO label, not by
retrieval) and must be verified by a teammate before the final report.

Current set: 25 job queries (5 French) over 20 USAJOBS postings, 14 ESCO, 4 ESCO no-answer. J01–J10 form the
`prelim` batch (5 postings); J11–J25 were written after the corpus was frozen at 20 postings.
