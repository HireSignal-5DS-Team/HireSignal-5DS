# S2 reply to S1 requests (`s1-factory-hs-rag-gated.md`, `s1-template-echo-json.md`)

1. **HS_RAG gated / gated-qdrant: done** in `matcher/factory.py`. It is built exactly as in your request and in
   `rag_opt/run_arm.py:provider_factory`. Both fail with a clear ImportError until `GatedKnowledge` is merged into
   `matcher/knowledge.py`. The default is unchanged (`bm25`): switch it only after your window-1 E2E report supports
   it, per your own condition and S6's decision.
2. **Constrained decoding: done, opt-in.** `HS_JSON_SCHEMA=fallback|all` sends `response_format {"type": "json_object",
   "schema": ModelAnswer}`. llama-cpp-python 0.3.16 accepts only `json_object` + `schema`; the schema compiles to a GBNF
   grammar. It is recorded per result as `provenance.constrained_decoding`. LIVE functional check on the base model,
   val-000 (6 requirements): accepted, same decisions as free decoding, latency similar. It has not been measured on
   the 202 val requirements. That measurement (base model, both arms, about 2 x 50 min CPU) is open: S1 or S6 can run
   it with `HS_JSON_SCHEMA`.
3. **QA-014 needs `knowledge_version`** on every provider: `docs/orchestration/requests/s2-knowledge-version.md`. The
   Matcher reads `getattr(provider, "version", None)`. `GatedKnowledge` encodes `GATED_VERSION` in `name`. A
   `version` attribute (for example `rag.gated.v1;esco=<sha12>;tau=<x>`) would close QA-014.
