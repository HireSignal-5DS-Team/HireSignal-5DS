"""Output adapters. Retrieval itself is unchanged; these only reshape `Retriever.search` output.

- to_knowledge_refs: the Qwen3-4B Matcher's KnowledgeRef objects (contracts/KnowledgeRef.schema.json, real schema).
- mock_dali_search: MOCK for Dali's backend. His schemas (pipeline v0.2.0, rag_search v1.1.0) are not in the repository,
  so this response format is ours, labelled "mock", and must be replaced once they are committed. No field is guessed
  from his schemas.
"""


def to_knowledge_refs(results, retrieval):
    """results: [(chunk, score)] from Retriever.search; retrieval: e.g. 'rag.dense.e5-small'."""
    refs = []
    for c, s in results:
        text = c["text"]
        aliases = []
        if c["source_type"] == "esco" and "Also known as: " in text:
            aliases = [a.strip() for a in text.split("Also known as: ", 1)[1].split(". ", 1)[0].split(";") if a.strip()]
        refs.append({"source_type": c["source_type"], "source_id": c["doc_id"], "title": c["title"], "text": text,
                     "url": c.get("url"), "aliases": aliases, "relevance_score": round(float(s), 4), "retrieval": retrieval})
    return refs


def mock_dali_search(query, job_id, top_k, search_output, retrieval):
    return {"schema_version": "mock-0 (Dali's rag_search v1.1.0 not available)", "query": query, "job_id": job_id,
            "top_k": top_k, "status": search_output["status"],
            "knowledge_refs": to_knowledge_refs(search_output["results"], retrieval)}
