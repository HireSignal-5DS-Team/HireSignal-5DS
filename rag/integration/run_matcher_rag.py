"""Run the Qwen3-4B Matcher benchmark (teammate code, unmodified) with a chosen RAG provider.

The Matcher code is used from a checkout of branch claude/kind-albattani-k7qlt9 (MATCHER_DIR), never modified.
  --rag none   -> NoKnowledge                                   (configuration A)
  --rag bm25   -> the Matcher's own RagKnowledge (BM25, ESCO), reading THIS repository's rag/   (configuration B)
  --rag dense  -> DenseKnowledge below: same ESCO collection and query text, e5-small dense, top-k (configuration C)
All other arguments are passed to `python -m benchmark.run` unchanged (backend, base URL, split, adapter, run id...),
so the same script compares base vs fine-tuned (LoRA) models once an adapter exists.

  MATCHER_DIR=/path/to/matcher-checkout python rag/integration/run_matcher_rag.py --rag dense -- \
      --backend openai --base-url http://127.0.0.1:8080/v1 --model Qwen/Qwen3-4B-Instruct-2507 \
      --revision <gguf revision> --split val --run-id qwen3-4b-q4-dense-val --out-root rag/integration/results
"""
import os
import sys
from pathlib import Path

RAG = Path(__file__).resolve().parents[1]
MATCHER = Path(os.environ["MATCHER_DIR"])
os.environ.setdefault("HIRESIGNAL_RAG_DIR", str(RAG))
sys.path.insert(0, str(MATCHER))
sys.path.append(str(RAG))  # appended: the Matcher's own packages win on name clashes

import benchmark.run as br  # noqa: E402
from matcher.knowledge import esco_aliases, query_for  # noqa: E402
from matcher.schemas import KnowledgeRef  # noqa: E402


class DenseKnowledge:
    """Same contract as the Matcher's RagKnowledge (name, lookup(req, k) -> [KnowledgeRef]), dense e5-small search."""
    name = "rag.dense.e5-small"

    def __init__(self):
        from corpus import load_esco
        from retrieval import Retriever

        chunks = [{**e, "chunk_id": e["doc_id"], "section": None, "start": None, "end": None} for e in load_esco()]
        self.retriever = Retriever(chunks, model="e5-small", store_path=RAG / "index")  # persisted, reused

    def lookup(self, req, k=3):
        out = self.retriever.search(query_for(req), k=k, mode="dense", filters={"source_type": "esco"})
        return [KnowledgeRef(source_type="esco", source_id=c["doc_id"], title=c["title"], text=c["text"], url=c["url"],
                             aliases=esco_aliases(c["text"]), relevance_score=round(s, 4), retrieval=self.name)
                for c, s in out["results"]]


if __name__ == "__main__":
    i = sys.argv.index("--rag")
    mode = sys.argv[i + 1]
    rest = sys.argv[sys.argv.index("--") + 1:]
    if mode == "dense":
        br.RagKnowledge = DenseKnowledge
    br.run(br.parse_args(rest + ["--knowledge", "none" if mode == "none" else "rag"]))
