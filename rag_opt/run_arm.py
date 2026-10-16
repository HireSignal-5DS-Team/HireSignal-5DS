"""Run ONE knowledge arm of the end-to-end RAG comparison with the frozen benchmark loop (benchmark/run.py, unchanged).

Arms (knowledge provider behind lookup(req, k=3, job_id=None)):
  none          NoKnowledge                                   (benchmark.run --knowledge none)
  bm25          legacy RagKnowledge, rag.bm25, k=3            (benchmark.run --knowledge rag; the B/B' arm)
  gated         GatedKnowledge rag.gated.v1+bm25              (this session's provider)
  gated-qdrant  GatedKnowledge with Qdrant/e5-small candidates (dense_tau from rag/experiments/exp03 thresholds)

benchmark.run builds `RagKnowledge()` when --knowledge rag; for the gated arms that constructor is replaced by the
gated provider before the loop starts, so prediction records, metrics, resume rules and config.json are produced by
the same frozen code for every arm (config.json records the provider name, so a resume into another arm fails).

Extra provenance (provenance.json next to predictions.jsonl): arm, provider name and parameters, ESCO file
SHA-256, git commit, the server's /v1/models answer, adapter provenance when given, and the peak RSS of the model
server process (sampled every 2 s; the client RSS is in metrics.json).

  python -m rag_opt.run_arm --arm gated --backend openai --model Qwen/Qwen3-4B-Instruct-2507+lora \
      --base-url http://127.0.0.1:8081/v1 --run-id lora-gated-val --out-root rag_opt/results/e2e
  python -m rag_opt.run_arm --arm gated --backend mock_gold --run-id MOCK-gated --limit 2   # plumbing check, MOCK
"""
import argparse
import hashlib
import json
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import benchmark.run as bench  # noqa: E402
from matcher.knowledge import GatedKnowledge  # noqa: E402

ARMS = ("none", "bm25", "gated", "gated-qdrant")
THRESHOLDS = ROOT / "rag/experiments/exp03_optimization/thresholds.json"


def provider_factory(arm):
    """Constructor used in place of benchmark.run.RagKnowledge; None = keep benchmark.run's own choice."""
    if arm == "gated":
        return lambda: GatedKnowledge()
    if arm == "gated-qdrant":
        def make():
            sys.path.insert(0, str(ROOT / "rag"))
            from corpus import build_chunks
            from retrieval import Retriever

            tau = json.loads(THRESHOLDS.read_text())["structure@300 | e5-small"]["esco"]
            r = Retriever(build_chunks("structure"), model="e5-small", store_path=ROOT / "rag/index")
            return GatedKnowledge(retriever=r, mode="dense", dense_tau=tau)
        return make
    return None


def server_info(base_url):
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/models", timeout=5) as r:
            return json.loads(r.read())
    except Exception as err:  # noqa: BLE001 - provenance only
        return {"error": f"{type(err).__name__}: {err}"}


class ServerRSS(threading.Thread):
    """Peak RSS of the process listening on the server port (llama.cpp); None when it cannot be found."""

    def __init__(self, base_url):
        super().__init__(daemon=True)
        from urllib.parse import urlparse

        self.port = urlparse(base_url).port if base_url else None
        self.peak_mb, self.stop = None, threading.Event()

    def _proc(self):
        import psutil

        for c in psutil.net_connections(kind="tcp"):
            if c.laddr and c.laddr.port == self.port and c.status == psutil.CONN_LISTEN and c.pid:
                return psutil.Process(c.pid)
        return None

    def run(self):
        try:
            p = self._proc() if self.port else None
            while p is not None and not self.stop.is_set():
                mb = p.memory_info().rss / 2**20
                self.peak_mb = max(self.peak_mb or 0.0, round(mb, 1))
                self.stop.wait(2.0)
        except Exception:  # noqa: BLE001 - psutil missing or no permission: leave None
            pass


def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arm", required=True, choices=ARMS)
    ap.add_argument("--adapter-provenance", help="json with the adapter repo + sha (e.g. benchmark/results/adapter/hs_lora_provenance.json)")
    a, rest = ap.parse_known_args(argv)
    if "--knowledge" in rest:
        ap.error("--knowledge is set by --arm")
    if "--split" in rest and rest[rest.index("--split") + 1] == "test":
        ap.error("the test split stays locked for S1 runs (only the orchestrator unlocks it)")
    b = bench.parse_args([*rest, "--knowledge", "none" if a.arm == "none" else "rag"])
    factory, original = provider_factory(a.arm), bench.RagKnowledge
    out = Path(b.out_root) / b.run_id
    out.mkdir(parents=True, exist_ok=True)
    rss = ServerRSS(b.base_url if b.backend == "openai" else None)
    rss.start()
    t0 = time.time()
    try:
        if factory is not None:
            bench.RagKnowledge = factory  # the frozen loop calls RagKnowledge() for --knowledge rag
        m = bench.run(b)
    finally:
        bench.RagKnowledge = original
        rss.stop.set()
    cfg = json.loads((out / "config.json").read_text())
    prov = {"arm": a.arm, "knowledge_provider": cfg["knowledge"], "k": b.k,
            "label": "MOCK (not a model result)" if b.backend.startswith("mock") else
                     ("LIVE model run" if cfg["backend"].get("is_model") else "deterministic baseline (not a model)"),
            "esco_sha256": sha256(ROOT / "rag/data/esco/esco_ict_skills.jsonl"),
            "gated_thresholds_sha256": sha256(THRESHOLDS) if a.arm == "gated-qdrant" else None,
            "git_commit": cfg.get("git_commit"), "dataset_sha256": cfg.get("dataset_sha256"),
            "server_models": server_info(b.base_url) if b.backend == "openai" else None,
            "server_peak_rss_mb": rss.peak_mb, "client_peak_rss_mb": m.get("peak_rss_mb"),
            "adapter": json.loads(Path(a.adapter_provenance).read_text()) if a.adapter_provenance else None,
            "wall_s": round(time.time() - t0, 1)}
    (out / "provenance.json").write_text(json.dumps(prov, indent=2) + "\n")
    return m


if __name__ == "__main__":
    main()
