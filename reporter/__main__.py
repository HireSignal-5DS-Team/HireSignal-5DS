"""Write the HireSignal report (JSON + HTML + Markdown) from a saved Pipeline.run() output.

    python -m reporter out/val-000/report.json --out out/val-000            # deterministic
    HS_REPORTER_SLM=on python -m reporter out/val-000/report.json --out out/val-000   # + tiny SLM text (validated)
"""
import argparse
import json
from pathlib import Path

from .writer import slm_from_env, write_files


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pipeline_json", help="Pipeline.run() output (scripts/run_pipeline.py writes it as report.json)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--job-title", help="job title given by the caller (the pipeline output has none)")
    a = ap.parse_args(argv)
    out = json.loads(Path(a.pipeline_json).read_text())
    slm, status = slm_from_env()
    rep = write_files(out, a.out, slm=slm, slm_status=status, job_title=a.job_title)
    p = rep.provenance
    print(f"wrote {a.out}/report.report.json, report.html, report.slm.md; SLM {p.slm_status}: "
          f"{p.sections_slm}/{p.sections_total} sections by the SLM, {p.sections_fallback} deterministic fallback")


if __name__ == "__main__":
    main()
