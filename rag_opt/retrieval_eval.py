"""Retrieval-only metrics of the Matcher knowledge providers (no LLM).

    python -m rag_opt.retrieval_eval            # BM25 providers: legacy rag.bm25 vs rag.gated.v1+bm25
    nice -n 19 python -m rag_opt.retrieval_eval --dense   # adds legacy dense (QdrantKnowledge) and gated + Qdrant
                                                          # (needs sentence-transformers + intfloat/multilingual-e5-small)
Writes rag_opt/results/retrieval_metrics{,_dense}.{json,md}.

Query sets
1. bench-v1 val, 202 requirements, through the frozen lookup(req, k=3) interface, in two query modes:
   - terms: the Requirement as the Matcher sends it (skill_terms present, the production case);
   - text : skill_terms removed, so retrieval works from the requirement sentence only (harder).
   Gold concept: the ESCO concept whose preferred/alternative label equals the skill term. For the alias and
   absent-skill items this is the generator's ground truth (benchmark/make_dataset.py: ALIASES and NEAR use ESCO
   preferred labels). Requirements without such a concept are "should abstain" (no relevant concept exists).
   Note: the gated provider uses exact label matching, so its terms-mode recall on this set is high by
   construction; the text mode and set 2 are the non-trivial checks.
2. Team-reviewed natural-language ESCO queries (never the sealed final test): rag/eval/queries_reviewed.jsonl,
   rag/experiments/exp02_benchmark/holdout_queries.jsonl, rag/experiments/exp03_optimization/calibration_queries.jsonl
   (types esco and none). Gold = their gold_uris restricted to the indexed ESCO subset; queries whose gold concept is
   not in the subset are counted and skipped; type none = should abstain.

Metrics: recall@1, recall@3 and MRR on queries with a gold concept (an abstention scores 0); abstention precision
(abstained queries that indeed have no gold concept), abstention recall (no-gold queries abstained on), false
abstention rate, off-target references per query, knowledge characters per query, lookup latency.
Paired: McNemar on hit@1 and a paired bootstrap 95% CI (2,000 resamples, seed 0) of the MRR difference.
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from matcher.knowledge import GatedKnowledge, RagKnowledge, surface  # noqa: E402
from matcher.schemas import Requirement  # noqa: E402
from rag.significance import mcnemar_exact  # noqa: E402

TEAM_SETS = ["rag/eval/queries_reviewed.jsonl", "rag/experiments/exp02_benchmark/holdout_queries.jsonl",
             "rag/experiments/exp03_optimization/calibration_queries.jsonl"]
SEALED = "final_test_queries.jsonl"
OUT = ROOT / "rag_opt/results"


def bench_queries(gated, split="val"):
    rows = []
    for line in (ROOT / f"benchmark/data/{split}.jsonl").read_text(encoding="utf-8").splitlines():
        c = json.loads(line)
        for r in c["job"]["requirements"]:
            req = Requirement(**r)
            gold = {i for t in req.skill_terms for i in gated.surface_index.get(surface(t), [])}
            rows.append({"qid": f"{c['case_id']}/{req.req_id}", "req": req, "gold": gold, "category": req.category,
                         "tags": c["gold"][req.req_id]["tags"]})
    return rows


def team_queries(gated):
    rows, skipped = [], []
    for f in TEAM_SETS:
        assert SEALED not in f
        for q in map(json.loads, (ROOT / f).read_text(encoding="utf-8").splitlines()):
            if q["type"] not in ("esco", "none"):
                continue
            gold = set(q.get("gold_uris") or [])
            if not gold and q.get("gold_labels"):
                gold = {i for lab in q["gold_labels"] for i in gated.surface_index.get(surface(lab), [])}
            if q["type"] == "esco" and not gold & set(gated.esco):
                skipped.append(q["qid"])
                continue
            req = Requirement(req_id=q["qid"], text=q["query"], category="skill", skill_terms=[])
            rows.append({"qid": q["qid"], "req": req, "gold": gold & set(gated.esco), "category": q["type"],
                         "tags": [q.get("lang", "en"), Path(f).stem]})
    return rows, skipped


def run_provider(provider, rows, mode, k=3):
    out = []
    for row in rows:
        req = row["req"] if mode == "terms" else row["req"].model_copy(update={"skill_terms": []})
        t0 = time.perf_counter()
        refs = provider.lookup(req, k=k)
        dt = time.perf_counter() - t0
        out.append({"qid": row["qid"], "ids": [x.source_id for x in refs], "chars": sum(len(x.text[:300]) for x in refs),
                    "latency_ms": dt * 1000})
    return out


def metrics(rows, res):
    g = [(row, r) for row, r in zip(rows, res) if row["gold"]]
    ng = [(row, r) for row, r in zip(rows, res) if not row["gold"]]
    abst = [(row, r) for row, r in zip(rows, res) if not r["ids"]]

    def rr(row, r):
        return next((1 / i for i, x in enumerate(r["ids"], 1) if x in row["gold"]), 0.0)

    lat = sorted(r["latency_ms"] for r in res)
    return {
        "n": len(rows), "n_with_gold": len(g), "n_no_gold": len(ng),
        "recall@1": round(sum(bool(set(r["ids"][:1]) & row["gold"]) for row, r in g) / len(g), 3) if g else None,
        "recall@3": round(sum(bool(set(r["ids"][:3]) & row["gold"]) for row, r in g) / len(g), 3) if g else None,
        "mrr": round(sum(rr(row, r) for row, r in g) / len(g), 3) if g else None,
        "false_abstention": round(sum(not r["ids"] for _, r in g) / len(g), 3) if g else None,
        "abstention_recall": round(sum(not r["ids"] for _, r in ng) / len(ng), 3) if ng else None,
        "abstention_precision": round(sum(not row["gold"] for row, _ in abst) / len(abst), 3) if abst else None,
        "n_abstained": len(abst),
        "off_target_refs_per_query": round(sum(sum(x not in row["gold"] for x in r["ids"]) for row, r in zip(rows, res))
                                           / len(rows), 3),
        "knowledge_chars_per_query": round(statistics.fmean(r["chars"] for r in res), 1),
        "latency_ms_p50": round(lat[len(lat) // 2], 2), "latency_ms_p95": round(lat[int(0.95 * (len(lat) - 1))], 2),
        "_rr": [rr(row, r) for row, r in g], "_hit1": [bool(set(r["ids"][:1]) & row["gold"]) for row, r in g],
    }


def paired(m_base, m_cand, n_boot=2000, seed=0):
    import numpy as np

    a, b = np.array(m_base["_rr"]), np.array(m_cand["_rr"])
    if not len(a):
        return None
    rng = np.random.default_rng(seed)
    d = [float((b[s] - a[s]).mean()) for s in (rng.integers(0, len(a), len(a)) for _ in range(n_boot))]
    x, y, p = mcnemar_exact(m_base["_hit1"], m_cand["_hit1"])
    return {"mrr_delta": round(float(b.mean() - a.mean()), 3),
            "ci95": [round(float(np.percentile(d, 2.5)), 3), round(float(np.percentile(d, 97.5)), 3)],
            "hit1_base_only": x, "hit1_cand_only": y, "mcnemar_p": round(p, 4)}


def groups_of(rows, kind):
    gs = {"all": list(range(len(rows)))}
    if kind == "bench":
        for name, pred in [("alias items", lambda r: "equivalent_skill_alias" in r["tags"]),
                           ("absent-skill items", lambda r: "rag_suggests_absent_skill" in r["tags"]),
                           *[(f"category={c}", (lambda c: lambda r: r["category"] == c)(c))
                             for c in ("skill", "experience", "certification", "language", "education")]]:
            gs[name] = [i for i, r in enumerate(rows) if pred(r)]
    else:
        gs["english"] = [i for i, r in enumerate(rows) if "en" in r["tags"]]
        gs["french"] = [i for i, r in enumerate(rows) if "fr" in r["tags"]]
    return gs


def build_providers(dense):
    gated = GatedKnowledge()
    prov = {"legacy rag.bm25 (k=3)": RagKnowledge(), gated.name: gated}
    if dense:
        sys.path.insert(0, str(ROOT / "rag"))
        from corpus import build_chunks
        from retrieval import Retriever

        from matcher.knowledge import QdrantKnowledge

        thr = json.loads((ROOT / "rag/experiments/exp03_optimization/thresholds.json").read_text())
        tau = thr["structure@300 | e5-small"]["esco"]
        r = Retriever(build_chunks("structure"), model="e5-small", store_path=ROOT / "rag/index")
        prov["legacy rag.qdrant.e5-small (k=3)"] = QdrantKnowledge(retriever=r)
        g2 = GatedKnowledge(retriever=r, mode="dense", dense_tau=tau)
        prov[g2.name + f" (tau={tau:.4f})"] = g2
        g3 = GatedKnowledge(retriever=r, mode="dense", dense_tau=None)
        prov[g3.name + " (lexical cut-off only)"] = g3
    return gated, prov


def evaluate(dense=False):
    gated, providers = build_providers(dense)
    bench = bench_queries(gated)
    team, skipped = team_queries(gated)
    out = {"label": "retrieval only (no LLM); rankings are deterministic, latency is measured on this CPU and varies", "providers": list(providers),
           "team_queries_skipped_gold_not_in_index": skipped, "sets": {}}
    base_name = "legacy rag.bm25 (k=3)"
    for set_name, rows, modes, kind in (("bench-v1 val (202 requirements)", bench, ("terms", "text"), "bench"),
                                        ("team-reviewed NL ESCO queries", team, ("text",), "team")):
        for mode in modes:
            key = f"{set_name} | query={mode}"
            res = {p: run_provider(prov, rows, mode) for p, prov in providers.items()}
            block = {}
            for gname, idx in groups_of(rows, kind).items():
                sub_rows = [rows[i] for i in idx]
                ms = {p: metrics(sub_rows, [res[p][i] for i in idx]) for p in providers}
                block[gname] = {p: {k: v for k, v in m.items() if not k.startswith("_")} for p, m in ms.items()}
                block[gname]["paired_vs_legacy_bm25"] = {p: paired(ms[base_name], ms[p]) for p in providers
                                                        if p != base_name}
            out["sets"][key] = block
    return out


def to_markdown(out):
    cols = ["n", "recall@1", "recall@3", "mrr", "false_abstention", "abstention_precision", "abstention_recall",
            "off_target_refs_per_query", "knowledge_chars_per_query", "latency_ms_p50", "latency_ms_p95"]
    L = ["# Knowledge retrieval metrics (generated by `python -m rag_opt.retrieval_eval`)", "", f"_{out['label']}_", "",
         f"Team queries skipped (gold concept outside the indexed ESCO subset): {out['team_queries_skipped_gold_not_in_index']}"]
    for key, block in out["sets"].items():
        L += ["", f"## {key}"]
        for gname, ms in block.items():
            L += ["", f"### {gname}", "", "| provider | " + " | ".join(cols) + " |", "|---" * (len(cols) + 1) + "|"]
            for p, m in ms.items():
                if p == "paired_vs_legacy_bm25":
                    continue
                L.append(f"| {p} | " + " | ".join("n/a" if m.get(c) is None else str(m.get(c)) for c in cols) + " |")
            for p, st in ms["paired_vs_legacy_bm25"].items():
                if st:
                    L.append(f"\n{p} vs legacy BM25: ΔMRR {st['mrr_delta']:+.3f} [{st['ci95'][0]:+.3f}, {st['ci95'][1]:+.3f}], "
                             f"hit@1 legacy-only {st['hit1_base_only']} / new-only {st['hit1_cand_only']}, McNemar p {st['mcnemar_p']}")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dense", action="store_true", help="also evaluate the Qdrant/e5-small providers")
    a = ap.parse_args()
    out = evaluate(a.dense)
    OUT.mkdir(parents=True, exist_ok=True)
    stem = "retrieval_metrics" + ("_dense" if a.dense else "")
    (OUT / f"{stem}.json").write_text(json.dumps(out, indent=1) + "\n")
    (OUT / f"{stem}.md").write_text(to_markdown(out))
    print(to_markdown(out))


if __name__ == "__main__":
    main()
