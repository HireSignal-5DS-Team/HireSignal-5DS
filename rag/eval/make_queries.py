# Adapted from team V2: rag/eval/queries_reviewed.jsonl (the 14 English ESCO queries, copied with their gold) (feature/agent-integration @ a5a03ff)
r"""Retrieval evaluation set with known answers (T09 Part B) -> rag/eval/queries.jsonl.

Sources:
- v2_reviewed: V2's reviewed English ESCO queries (gold by V2 review, approved by the V2 project owner).
- t06_error:   the alias / buried-term misses of the T06 Matcher error analysis (ERRORS.md), written as the term a CV
               or a requirement uses.
- gold_req:    skill phrases of our 28 gold requirements (data/labels/gold/requirements_gold.csv).
Gold for t06_error / gold_req: drafted by the Developer (AI) from exact ESCO labels BEFORE any retrieval run, not
human-verified. ESCO v1.1.1 has no concept for some tools (Spark, Kubernetes, data lake, AWS, PyTorch, microservices):
their gold is the closest broader ESCO concept, noted per query. Any listed URI counts as a hit.
Split: alternating dev / test inside each source (fixed before measuring).
Usage: .venv\Scripts\python rag\eval\make_queries.py
"""
import json
import os
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
V2_REVIEWED = Path(os.environ.get("V2_REPO", "")) / "rag/eval/queries_reviewed.jsonl"  # optional, to refresh the copy
V2_COPY = HERE / "v2_queries_reviewed_en.jsonl"  # read-only copy of the English ESCO part (rule 6)

OURS = [  # (qid, source, query, gold labels, note)
    ("O01", "t06_error", "PL/SQL", ["SQL", "query languages"], "P12 r2: 'PL / SQL' not read as SQL"),
    ("O02", "t06_error", "Databricks Lakehouse Fundamentals", ["data warehouse"], "P15 r1; no data-lake concept in ESCO v1.1.1: closest"),
    ("O03", "t06_error", "AWS RDS, AWS Aurora Postgres", ["cloud technologies", "database management systems"], "P20 r4; no AWS concept"),
    ("O04", "t06_error", "PyTorch", ["deep learning", "machine learning"], "no PyTorch concept: closest"),
    ("O05", "t06_error", "TensorFlow", ["deep learning", "machine learning"], "P21 r4; no TensorFlow concept: closest"),
    ("O06", "t06_error", "DWBI/DWH/ETL projects", ["data warehouse", "data extraction, transformation and loading tools"], "P13 r1"),
    ("O07", "t06_error", "ARIMA time series forecasting", ["carry out statistical forecasts"], "P06 r3"),
    ("O08", "t06_error", "Monte Carlo Markov Chain", ["probability theory", "statistics"], "P06 r3/r4"),
    ("O09", "t06_error", "Azure and AWS services", ["cloud technologies"], "P15 r4"),
    ("O10", "gold_req", "Data Warehousing", ["data warehouse"], "J2 r1"),
    ("O11", "gold_req", "Data Lakes", ["data warehouse"], "J2 r1; no data-lake concept: closest"),
    ("O12", "gold_req", "probability theory and statistics", ["probability theory", "statistics"], "J1 r2"),
    ("O13", "gold_req", "Bayesian methods", ["probability theory", "statistics"], "J1 r3"),
    ("O14", "gold_req", "Amazon SageMaker", ["cloud technologies", "machine learning"], "J1 r5; no AWS concept"),
    ("O15", "gold_req", "PySpark", ["Python (computer programming)", "analyse big data"], "J1 r6; no Spark concept"),
    ("O16", "gold_req", "strong working knowledge of SQL", ["SQL"], "J1 r7"),
    ("O17", "gold_req", "GCP or another cloud provider", ["cloud technologies"], "J2 r4"),
    ("O18", "gold_req", "good spoken English", ["interact verbally in English", "understand spoken English", "English"], "J2 r5"),
    ("O19", "gold_req", "excellent Python coding skills", ["Python (computer programming)"], "J3 r3"),
    ("O20", "gold_req", "Gradient Boosting Trees", ["machine learning"], "J3 r2; no boosting concept: closest"),
    ("O21", "gold_req", "microservices architecture", ["software architecture models"], "J3 r6; no microservices concept: closest"),
    ("O22", "gold_req", "Docker", ["manage ICT virtualisation environments"], "J3 r6, J4 r4; no Docker concept: closest (as V2 N01)"),
    ("O23", "gold_req", "data pipelines or big data", ["data extraction, transformation and loading tools", "analyse big data", "Hadoop"], "J3 r7"),
    ("O24", "gold_req", "asynchronous programming", ["use concurrent programming"], "J4 r3"),
    ("O25", "gold_req", "collaborative filtering", ["build recommender systems"], "J4 r6"),
    ("O26", "gold_req", "data normalization", ["normalise data"], "J4 r6"),
    ("O27", "gold_req", "clustering", ["data mining", "machine learning", "algorithms"], "J4 r6"),
    ("O28", "gold_req", "AutoML flows or frameworks", ["machine learning"], "J3 r8; no AutoML concept: closest"),
    ("O29", "gold_req", "research business logic", ["analyse business processes", "business requirements techniques",
                                                     "analyse business requirements"], "J2 r6"),
    ("O30", "gold_req", "Experience with Machine Learning", ["machine learning", "utilise machine learning"], "J4 r5"),
    ("O31", "gold_req", "Ph.D. in Mathematics", ["mathematics"], "J1 r8"),
    ("O32", "gold_req", "feature engineering and data cleansing", ["perform data cleansing", "normalise data"], "J1 extra"),
]


def main():
    concepts = [json.loads(line) for line in open(ROOT / "rag/data/esco/esco_ict_graph.jsonl", encoding="utf-8")]
    by_label = {c["label"]: c["uri"] for c in concepts}
    if os.environ.get("V2_REPO") and V2_REVIEWED.exists():
        v2 = [json.loads(line) for line in open(V2_REVIEWED, encoding="utf-8")]
        v2 = [q for q in v2 if q["type"] == "esco" and q["lang"] == "en"]
        V2_COPY.write_text("".join(json.dumps(q, ensure_ascii=False) + "\n" for q in v2), encoding="utf-8")
    v2 = [json.loads(line) for line in open(V2_COPY, encoding="utf-8")]
    out = []
    for i, q in enumerate(v2):
        assert all(u in by_label.values() for u in q["gold_uris"]), q["qid"]
        out.append({"qid": q["qid"], "source": "v2_reviewed", "query": q["query"], "gold_labels": q["gold_labels"],
                    "gold_uris": q["gold_uris"], "split": "dev" if i % 2 == 0 else "test",
                    "how_made": "V2 reviewed query (" + q["review_decision"] + ")"})
    for src in ("t06_error", "gold_req"):
        for i, (qid, s, query, labels, note) in enumerate(x for x in OURS if x[1] == src):
            out.append({"qid": qid, "source": s, "query": query, "gold_labels": labels,
                        "gold_uris": [by_label[label] for label in labels], "split": "dev" if i % 2 == 0 else "test",
                        "how_made": f"drafted by the Developer from {note}; gold by exact ESCO label, before retrieval"})
    (HERE / "queries.jsonl").write_text("".join(json.dumps(q, ensure_ascii=False) + "\n" for q in out), encoding="utf-8")
    print(len(out), {s: sum(q["split"] == s for q in out) for s in ("dev", "test")},
          {s: sum(q["source"] == s for q in out) for s in ("v2_reviewed", "t06_error", "gold_req")})


if __name__ == "__main__":
    main()
