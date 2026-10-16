# Interface contracts

| File | Source | Status |
|---|---|---|
| `KnowledgeRef.schema.json` | Verbatim copy of `matcher/json_schemas/KnowledgeRef.schema.json` from branch `claude/kind-albattani-k7qlt9` (Matcher, commit `e584a13`), copied 2026-10-15 | Real schema used by the Qwen3-4B Matcher; our `/knowledge` output is validated against it in tests |
| Dali's `pipeline.schema.json` v0.2.0, `rag_search.schema.json` v1.1.0 | **Not in the repository** | Missing: `/mock/v1/search` is a clearly labelled mock until they are committed |

If the Matcher schema changes, copy the new file here; `tests/test_rag.py::test_knowledge_refs_match_matcher_schema` will fail on any mismatch.
