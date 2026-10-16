# Request from S2: knowledge provider `version` attribute (S1 owns `matcher/knowledge.py`)

Status: open. Not blocking: S2 continues with a compatible approach.

## Need

Contract 4 (provenance) asks every result to name the knowledge provider **and its version**. The Matcher records
`knowledge_provider = provider.name` and `knowledge_version = getattr(provider, "version", None)`
(`matcher/agent.py:Matcher.knowledge_info`). Today no provider defines `version`, so it is `null` in every report.

## Proposal (additive, no interface change)

Each provider sets a string attribute `version` that changes when its retrieval output can change, e.g.
- `RagKnowledge`: `"bm25s-<bm25s version>;esco=<sha256[:12] of esco_ict_skills.jsonl>;min_score=<x>"`
- `QdrantKnowledge`: `"e5-small;index=<index build id or sha>;k_job=<n>"`
- `NoKnowledge`: `"none"`; `FixtureKnowledge`: `"fixture"`.

`lookup(req, k=3, job_id=None) -> list[KnowledgeRef]` is unchanged. S2 tests treat `version` as optional.
