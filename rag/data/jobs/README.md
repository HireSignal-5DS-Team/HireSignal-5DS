# Job postings collection

One file per posting: `<job_id>.md`. The header is mandatory; `corpus.py` refuses to index a posting
without provenance.

```
---
job_id: usajobs-812345600
title: Data Scientist
organisation: U.S. Department of ...
source_url: https://www.usajobs.gov/job/812345600
retrieved: 2026-10-14
rights: public domain (work of the U.S. federal government, 17 U.S.C. 105)
---
<posting text copied verbatim, keep the original headings and bullets>
```

Rules:
- Copy the text verbatim. Do not edit, summarise or fix it: the chunking comparison depends on the real structure.
- Prefer sources with clear reuse rights: USAJOBS (US federal works are public domain) or EU institution and
  agency vacancy notices (EU reuse policy, attribution). For any other source, write the site's terms in `rights`
  and confirm with the team before committing.
- Remove recruiter names, e-mails and phone numbers (replace with `[contact removed]`).
- Freeze the collection before writing evaluation queries (see `../../eval/README.md`).
