"""Named RAG configurations. Select with RAG_PROFILE (api.py). Evidence: experiments/exp02_benchmark, exp03_optimization.

Only `baseline` was selected by the pre-registered rules (exp02 and exp03, both latency profiles). The others are
opt-in and labelled experimental: better on the dev set but not significantly, or not validated on natural queries.
"""
PROFILES = {
    "baseline": {
        "strategy": "structure", "model": "e5-small", "reranker": None, "top_n": None, "thresholds": None,
        "status": "selected: production default and fallback (dev Matcher MRR 0.865, p95 128 ms on 4-core CPU)"},
    "async-experimental": {
        "strategy": "parent_child", "model": "e5-base", "reranker": "mmarco", "top_n": 10, "thresholds": None,
        "status": "experimental: best dev MRR within the async budget (0.912, p95 1.06 s) but not significant vs baseline"},
    "baseline-abstain-experimental": {
        "strategy": "structure", "model": "e5-small", "reranker": None, "top_n": None,
        # calibrated on the template calibration split (exp03 thresholds.json); 8/40 natural dev queries wrongly abstained
        "thresholds": {"job": 0.829, "esco": 0.844},
        "status": "experimental: calibrated cosine abstention; too strict on natural queries, recalibration needed"},
}
