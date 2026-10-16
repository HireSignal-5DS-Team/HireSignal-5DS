"""HTTP presentation adapter for the existing HireSignal Report Writer.

No changes to Matcher, RAG, Judge, Bias or SLM modeling code.
Returns only validated final text, not rejected SLM generations.
"""
from __future__ import annotations

from functools import lru_cache

from reporter import slm_from_env, to_html, to_markdown, write


@lru_cache(maxsize=1)
def _reporter_model():
    """Cache the CPU Qwen3-0.6B inference object between API requests."""
    return slm_from_env()


def render_report(pipeline_output: dict, job_title: str) -> dict:
    try:
        slm, status = _reporter_model()
    except Exception as exc:
        # An unavailable SLM must not erase otherwise verified matching.
        slm, status = None, f"unavailable: {type(exc).__name__}"

    report = write(pipeline_output, slm=slm, slm_status=status, job_title=job_title)
    provenance = report.provenance
    return {
        "schema_version": report.schema_version,
        "executive_summary": {
            "text": report.executive_summary.text,
            "writer": report.executive_summary.writer,
        },
        "requirements": [
            {
                "req_id": item.req_id,
                "plain_note": {
                    "text": item.plain_note.text,
                    "writer": item.plain_note.writer,
                },
            }
            for item in report.requirements
        ],
        "provenance": {
            "slm_status": provenance.slm_status,
            "sections_total": provenance.sections_total,
            "sections_slm": provenance.sections_slm,
            "sections_fallback": provenance.sections_fallback,
            "model": provenance.slm.get("model") if provenance.slm else None,
            "any_mock": provenance.any_mock,
        },
        "html": to_html(report),
        "markdown": to_markdown(report),
    }
