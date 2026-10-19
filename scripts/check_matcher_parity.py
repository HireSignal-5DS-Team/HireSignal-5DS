"""Offline parity check: our Matcher prompt v1 + BM25-ESCO knowledge vs team V2 (read-only, no model calls).

Usage: .venv\Scripts\python -B scripts\check_matcher_parity.py <this repo> <V2 repo path>
Compares (1) system prompt text with V2 matcher/prompt.py SYSTEM, (2) each user message with V2 user_message(),
(3) our top-3 ESCO ids with the rag_refs V2 logged in benchmark/results/qwen3-4b-q4-rag-val/predictions.jsonl.
V2 prompt.py is exec-ed from source (no import of the V2 package, -B: no bytecode written into V2).
"""
import json, sys, types
from pathlib import Path
ROOT, V2 = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
import smoke_matcher as sm
from rag.bm25_esco import BM25EscoKnowledge
# V2 prompt module, loaded from source without package import side effects
src = (V2 / "matcher/prompt.py").read_text(encoding="utf-8"); ns = {}; exec(compile(src, "v2_prompt", "exec"), ns)
system, template = sm.load_prompt(ROOT / "prompts/matcher/v1.md")
print("system identical to V2 p1:", system == ns["SYSTEM"])
items, pool = sm.select_items(ROOT / "data/processed/bench-v1/val.jsonl", 30, 20261018)
kb = BM25EscoKnowledge()
v2pred = {(p["case_id"], p["req_id"]): p for p in map(json.loads, open(V2 / "benchmark/results/qwen3-4b-q4-rag-val/predictions.jsonl", encoding="utf-8"))}
same_refs = same_msg = 0
for it in items:
    refs = kb.lookup(it["req"], k=3)
    same_refs += [r["source_id"] for r in refs] == v2pred[(it["case_id"], it["req_id"])]["rag_refs"]
    R = types.SimpleNamespace(**{"min_years": None, **it["req"]})
    C = types.SimpleNamespace(text=it["cv_text"])
    Refs = [types.SimpleNamespace(source_id=r["source_id"], text=r["text"]) for r in refs]
    same_msg += sm.user_message(template, it["cv_text"], it["req"], refs) == ns["user_message"](C, R, Refs)
print(f"rag_refs identical to V2's logged refs: {same_refs}/30; user message identical to V2 user_message(): {same_msg}/30")
print("gold:", {c: sum(i['gold'] == c for i in items) for c in sm.CLASSES}, "pool", pool)
