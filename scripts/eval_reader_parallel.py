r"""T10b: late fusion, sequential vs parallel (OCR on CPU || vision model on GPU), on the 10 dev photos.

For each photo: read_cv(mode="late") with READER_PARALLEL=0 and =1 (order alternates per image), wall time per page,
and an ASSERT that both results are identical (text, routes, warnings, review reasons, page details except the vision
latency). A warm-up vision call runs first (CUDA warm-up, not counted). Run once per condition:
  --condition gpu_free         llama-server stopped
  --condition llama_running    llama-server running
  --condition full_stack       llama-server + station API with the Judge and the RAG embedder loaded on the GPU
                               (as in the n8n e2e; --limit 3: each page is slow there)
Needs our Ollama (scripts/start_ollama.ps1). Results: <out>/<condition>.json.

Usage: .venv\Scripts\python scripts\eval_reader_parallel.py --out eval\results\<date>_reader_parallel --condition gpu_free
"""
import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from eval_multimodal import SCANS, items  # noqa: E402
from PIL import Image  # noqa: E402
from services.reader import multimodal as mm  # noqa: E402
from services.reader import read_cv  # noqa: E402


def snapshot(r):
    details = [{k: v for k, v in d.items() if k != "vision_latency_s"} for d in r.page_details]
    return {"text": r.text, "routes": r.page_routes, "warnings": r.warnings, "review_reasons": r.review_reasons,
            "details": details}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--condition", required=True, choices=("gpu_free", "llama_running", "full_stack"))
    ap.add_argument("--limit", type=int, default=0, help="only the first N dev photos")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    dev = [it for it in items() if it["split"] == "dev"][: a.limit or None]
    mm.vision_call(Image.open(SCANS / dev[0]["file"]), "Read this.")  # warm-up, not counted
    rows = []
    for i, it in enumerate(dev):
        data = (SCANS / it["file"]).read_bytes()
        res, secs = {}, {}
        for flag in (("0", "1") if i % 2 == 0 else ("1", "0")):
            os.environ["READER_PARALLEL"] = flag
            t = time.perf_counter()
            r = read_cv(data, it["file"], mode="late")
            secs[flag] = round(time.perf_counter() - t, 2)
            res[flag] = snapshot(r)
        assert res["0"] == res["1"], f"output differs for {it['id']}"
        rows.append({"item": it["id"], "sequential_s": secs["0"], "parallel_s": secs["1"], "identical": True,
                     "route": res["1"]["routes"]})
        print(rows[-1], flush=True)
    seq, par = [r["sequential_s"] for r in rows], [r["parallel_s"] for r in rows]
    summary = {"condition": a.condition, "label": "real-GPU (RTX 4050 6 GB) + real-CPU (Tesseract)", "pages": len(rows),
               "identical_outputs": f"{sum(r['identical'] for r in rows)}/{len(rows)}",
               "sequential_s_per_page_mean": round(statistics.mean(seq), 2),
               "parallel_s_per_page_mean": round(statistics.mean(par), 2),
               "sequential_s_per_page_median": round(statistics.median(seq), 2),
               "parallel_s_per_page_median": round(statistics.median(par), 2),
               "speedup_mean": round(statistics.mean(seq) / statistics.mean(par), 2), "rows": rows}
    (out / f"{a.condition}.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print({k: v for k, v in summary.items() if k != "rows"})


if __name__ == "__main__":
    main()
