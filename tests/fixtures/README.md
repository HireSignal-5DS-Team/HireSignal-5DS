Test fixtures copied from team V2 (feature/agent-integration @ a5a03ff), read-only originals:
- `job/offers/*.txt`, `job/gold/*.json`: V2 `eval/job_agent/` — 10 real USAJOBS offers (US government, public domain) and V2's hand-made gold cards.
- `job/job_post.example.txt`, `job/job_requirements.example.json`: V2 `examples/` (synthetic example).
- `profile/cvs/*.txt`, `profile/gold/*.json`: V2 `eval/profile_agent/cvs` and `eval/profile_agent/gold` — 10 self-written synthetic EN/FR CVs with hand-made gold identity (`must_hide`, `other_people`, `must_keep`). Adapted from team V2: eval/profile_agent/ (feature/agent-integration @ a5a03ff). Files copied unchanged (a header line inside a CV would change the anonymiser input).
