"""HireSignal Report Writer: deterministic report (JSON / HTML / Markdown) + optional tiny-SLM text with validation.

    from reporter import write, to_html, to_markdown
    rep = write(pipeline_output)                 # deterministic only
    rep = write(pipeline_output, slm=LlamaCppSLM())  # SLM summaries, validated, with fallback
"""
from .build import build_report
from .render import to_html, to_markdown
from .schema import DISCLAIMER, REPORT_SCHEMA_VERSION, Report
from .writer import slm_from_env, write, write_files

__all__ = ["DISCLAIMER", "REPORT_SCHEMA_VERSION", "Report", "build_report", "slm_from_env", "to_html", "to_markdown",
           "write", "write_files"]
